"""Importação insert-only de pacientes e agendamentos do Soul MV (spec §4.3)."""
from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import TypeVar

from django.db import transaction
from django.utils import timezone

from core.models import Agendamento, ExecucaoImportacao, Paciente

from .leitor import LayoutInvalidoError, RegistroSoulMV, ler_conteudo, sha256_bytes

logger = logging.getLogger(__name__)

TAMANHO_LOTE = 500

T = TypeVar('T')


@dataclass(frozen=True)
class ResultadoPersistencia:
    pacientes_criados: int
    agendamentos_criados: int
    pacientes_vinculados: int


def _lotes(itens: Iterable[T], tamanho: int = TAMANHO_LOTE) -> Iterator[list[T]]:
    lote: list[T] = []
    for item in itens:
        lote.append(item)
        if len(lote) == tamanho:
            yield lote
            lote = []
    if lote:
        yield lote


def _pacientes_existentes(codigos: set[str], cpfs: set[str]) -> tuple[dict[str, Paciente], dict[str, Paciente]]:
    por_codigo: dict[str, Paciente] = {}
    por_cpf: dict[str, Paciente] = {}
    encontrados: dict[int, Paciente] = {}
    for lote in _lotes(sorted(codigos)):
        for p in Paciente.objects.filter(codigo_cidadao__in=lote):
            encontrados.setdefault(p.pk, p)
    for lote in _lotes(sorted(cpfs)):
        for p in Paciente.objects.filter(cpf__in=lote):
            encontrados.setdefault(p.pk, p)
    for p in encontrados.values():
        if p.codigo_cidadao:
            por_codigo[p.codigo_cidadao] = p
        if p.cpf:
            por_cpf[p.cpf] = p
    return por_codigo, por_cpf


def _novo_paciente(r: RegistroSoulMV) -> Paciente:
    return Paciente(
        nome=r.nome,
        nome_social=r.nome_social,
        data_nascimento=r.data_nascimento,
        cpf=r.cpf,
        cns=r.cns,
        codigo_cidadao=r.codigo_cidadao,
        origem=Paciente.ORIGEM_SOULMV,
    )


def _atribuir_pks(novos: list[Paciente]) -> None:
    """bulk_create não devolve PK no MySQL; recupera pelas chaves naturais (codigo_cidadao/CPF)."""
    pendentes = [p for p in novos if p.pk is None]
    if not pendentes:
        return
    por_codigo, por_cpf = _pacientes_existentes(
        {p.codigo_cidadao for p in pendentes if p.codigo_cidadao},
        {p.cpf for p in pendentes if p.cpf},
    )
    for p in pendentes:
        salvo = (por_codigo.get(p.codigo_cidadao) if p.codigo_cidadao else None) or por_cpf.get(p.cpf or '')
        if salvo is None:
            raise RuntimeError('Paciente recém-criado não encontrado após bulk_create.')
        p.pk = salvo.pk


def persistir(registros: list[RegistroSoulMV]) -> ResultadoPersistencia:
    """Insere pacientes inexistentes e agendamentos novos. Nunca altera nem remove registros existentes,
    exceto vincular o codigo_cidadao a um paciente manual (sem código) casado por CPF."""
    fuso = timezone.get_current_timezone()
    por_codigo, por_cpf = _pacientes_existentes(
        {r.codigo_cidadao for r in registros if r.codigo_cidadao},
        {r.cpf for r in registros if r.cpf},
    )

    novos: list[Paciente] = []
    vinculos: dict[int, str] = {}
    paciente_da_solicitacao: dict[str, tuple[RegistroSoulMV, Paciente]] = {}

    for r in registros:
        if r.solicitacao in paciente_da_solicitacao:
            continue
        paciente = por_codigo.get(r.codigo_cidadao) if r.codigo_cidadao else None
        if paciente is None and r.cpf:
            paciente = por_cpf.get(r.cpf)
            if (
                paciente is not None
                and paciente.pk is not None
                and r.codigo_cidadao
                and paciente.codigo_cidadao is None
                and paciente.origem == Paciente.ORIGEM_MANUAL
            ):
                vinculos[paciente.pk] = r.codigo_cidadao
                paciente.codigo_cidadao = r.codigo_cidadao
                por_codigo[r.codigo_cidadao] = paciente
        if paciente is None:
            paciente = _novo_paciente(r)
            novos.append(paciente)
            if paciente.codigo_cidadao:
                por_codigo[paciente.codigo_cidadao] = paciente
            if paciente.cpf:
                por_cpf[paciente.cpf] = paciente
        paciente_da_solicitacao[r.solicitacao] = (r, paciente)

    with transaction.atomic():
        Paciente.objects.bulk_create(novos, batch_size=TAMANHO_LOTE)
        _atribuir_pks(novos)
        for pk, codigo in vinculos.items():
            Paciente.objects.filter(pk=pk, codigo_cidadao__isnull=True).update(codigo_cidadao=codigo)

        existentes: set[str] = set()
        for lote in _lotes(paciente_da_solicitacao):
            existentes.update(Agendamento.objects.filter(solicitacao__in=lote).values_list('solicitacao', flat=True))

        agendamentos = [
            Agendamento(
                paciente_id=paciente.pk,
                solicitacao=solicitacao,
                item_agendamento=r.item_agendamento,
                data_agenda=timezone.make_aware(r.data_agenda, fuso) if r.data_agenda else None,
            )
            for solicitacao, (r, paciente) in paciente_da_solicitacao.items()
            if solicitacao not in existentes
        ]
        Agendamento.objects.bulk_create(agendamentos, batch_size=TAMANHO_LOTE)

    return ResultadoPersistencia(len(novos), len(agendamentos), len(vinculos))


def _finalizar(execucao: ExecucaoImportacao, status: str, erro: str = '') -> ExecucaoImportacao:
    execucao.status = status
    execucao.erro = erro
    execucao.finalizado_em = timezone.now()
    execucao.save()
    return execucao


def _ultima_execucao_com_sucesso() -> ExecucaoImportacao | None:
    return (
        ExecucaoImportacao.objects.filter(status=ExecucaoImportacao.STATUS_SUCESSO)
        .order_by('-iniciado_em', '-pk')
        .first()
    )


def importar_conteudo(conteudo: bytes, nome_arquivo: str, *, forcar: bool = False) -> ExecucaoImportacao:
    execucao = ExecucaoImportacao.objects.create(arquivo=nome_arquivo, sha256=sha256_bytes(conteudo))

    ultima = _ultima_execucao_com_sucesso()
    if not forcar and ultima is not None and ultima.sha256 == execucao.sha256:
        return _finalizar(execucao, ExecucaoImportacao.STATUS_IGNORADO, f'Mesmo arquivo da execução #{ultima.pk}.')

    try:
        leitura = ler_conteudo(conteudo)
    except LayoutInvalidoError as exc:
        return _finalizar(execucao, ExecucaoImportacao.STATUS_ERRO, str(exc))

    execucao.linhas_lidas = leitura.linhas_lidas
    execucao.linhas_rejeitadas = len(leitura.rejeicoes)
    execucao.detalhes_rejeicao = [r.as_dict() for r in leitura.rejeicoes]

    if leitura.linhas_lidas == 0:
        return _finalizar(execucao, ExecucaoImportacao.STATUS_ERRO, 'CSV sem linhas de dados.')
    if not leitura.registros:
        return _finalizar(execucao, ExecucaoImportacao.STATUS_ERRO, 'Nenhuma linha válida no CSV.')

    try:
        resultado = persistir(leitura.registros)
    except Exception as exc:
        logger.exception('Falha ao persistir importação Soul MV (execução #%s)', execucao.pk)
        return _finalizar(
            execucao,
            ExecucaoImportacao.STATUS_ERRO,
            f'{type(exc).__name__}: falha ao gravar no banco (detalhes no log do servidor).',
        )

    execucao.pacientes_criados = resultado.pacientes_criados
    execucao.agendamentos_criados = resultado.agendamentos_criados
    logger.info(
        'Importação Soul MV #%s: %s pacientes, %s agendamentos, %s vínculos, %s rejeitadas',
        execucao.pk,
        resultado.pacientes_criados,
        resultado.agendamentos_criados,
        resultado.pacientes_vinculados,
        execucao.linhas_rejeitadas,
    )
    return _finalizar(execucao, ExecucaoImportacao.STATUS_SUCESSO)


def registrar_falha(arquivo: str, erro: str) -> ExecucaoImportacao:
    """Registra uma execução que falhou antes da importação (ex.: extração)."""
    execucao = ExecucaoImportacao.objects.create(arquivo=arquivo)
    return _finalizar(execucao, ExecucaoImportacao.STATUS_ERRO, erro)


def marcar_execucoes_expiradas(limite: timedelta) -> int:
    """Execuções presas em 'executando' além do limite são consideradas falhas (spec §5)."""
    agora = timezone.now()
    return ExecucaoImportacao.objects.filter(
        status=ExecucaoImportacao.STATUS_EXECUTANDO, iniciado_em__lt=agora - limite
    ).update(
        status=ExecucaoImportacao.STATUS_ERRO,
        finalizado_em=agora,
        erro=f'Execução excedeu {int(limite.total_seconds() // 60)} min sem finalizar.',
    )


def importar_arquivo(caminho: str | Path, *, forcar: bool = False) -> ExecucaoImportacao:
    caminho = Path(caminho)
    return importar_conteudo(caminho.read_bytes(), str(caminho), forcar=forcar)
