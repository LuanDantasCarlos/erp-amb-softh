"""BPA-I — Solicitação de Procedimento (A4 retrato). Spec §5.1."""
from __future__ import annotations

from reportlab.lib.pagesizes import A4

from .base import Desenho, LayoutGerado

NOME = 'BPA-I - Solicitação de Procedimento'
ARQUIVO = 'bpai_solicitacao_procedimento.pdf'

MARGEM = 36
LINHA = 19
TITULO = 13

RACA_COR = [
    ('01', 'Branca'), ('02', 'Preta'), ('03', 'Parda'), ('04', 'Amarela'), ('05', 'Indígena'), ('99', 'Sem informação'),
]
CARATER_ATENDIMENTO = [
    ('01', 'Eletivo'), ('02', 'Urgência'), ('03', 'Acidente no local de trabalho'), ('04', 'Acidente de trajeto'),
    ('05', 'Outros acidentes de trânsito'), ('06', 'Outras lesões/envenenamentos'),
]


def _opcoes_codigo(itens):
    return [{'id': codigo, 'texto': f'{codigo} - {texto}'} for codigo, texto in itens]


def construir() -> LayoutGerado:
    largura, altura = A4
    d = Desenho(largura, altura)
    x0, x1 = MARGEM, largura - MARGEM
    xi, xf = x0 + 6, x1 - 6  # área interna dos quadros

    def secao(y: float, titulo: str, altura_secao: float) -> float:
        d.retangulo(x0, y, x1 - x0, altura_secao)
        d.texto(xi, y + TITULO, titulo, 10, negrito=True)
        return y + TITULO + LINHA  # linha de base da primeira linha

    # Cabeçalho
    altura_logo = d.imagem('logo_sus.png', x0, 26, 110)
    d.texto((x0 + 110 + x1) / 2, 26 + altura_logo / 2 + 5, 'Solicitação de Procedimento (BPA-I)', 14,
            negrito=True, alinhamento='center')

    # Dados Operacionais
    y = 82
    altura_secao = TITULO + 9 * LINHA + 8
    b = secao(y, 'Dados Operacionais', altura_secao)
    d.rotulo_com_linha(xi, b, 'Mês/ano:', 200, 'Mês/ano', fonte='atendimento.mes_ano')
    d.rotulo_com_linha(215, b, 'Data do Atendimento:', xf, 'Data do Atendimento', fonte='atendimento.data')
    b += LINHA
    d.rotulo_com_linha(xi, b, 'Nome do Estabelecimento:', 400, 'Nome do Estabelecimento', fonte='estabelecimento.nome')
    d.rotulo_com_linha(410, b, 'CNES:', xf, 'CNES', fonte='estabelecimento.cnes')
    b += LINHA
    d.rotulo_com_linha(xi, b, 'CNS do Profissional:', 400, 'CNS do Profissional', fonte='medico.cns')
    d.rotulo_com_linha(410, b, 'CBO:', xf, 'CBO', fonte='medico.cbo')
    b += LINHA
    d.rotulo_com_linha(xi, b, 'Nome do Paciente:', 420, 'Nome do Paciente', fonte='paciente.nome', obrigatorio=True)
    xs = 430 + d.texto(430, b, 'Sexo:', 9) + 6
    pos_m = d.caixa_marcacao(xs, b)
    d.texto(xs + 11, b, 'M', 9)
    pos_f = d.caixa_marcacao(xs + 30, b)
    d.texto(xs + 41, b, 'F', 9)
    d.campo('Sexo', tipo='radio', fonte='paciente.sexo', opcoes=[
        {'id': 'M', 'texto': 'Masculino', 'posicao': pos_m},
        {'id': 'F', 'texto': 'Feminino', 'posicao': pos_f},
    ])
    d.posicao('Sexo', xs + 55, b, xf - xs - 55)
    b += LINHA
    d.rotulo_com_linha(xi, b, 'Nº CNS do Usuário:', 330, 'Nº CNS do Usuário', fonte='paciente.cns')
    d.rotulo_com_linha(340, b, 'Data Nascimento:', xf, 'Data Nascimento', fonte='paciente.nascimento_curto')
    b += LINHA
    d.rotulo_com_linha(xi, b, 'Raça/Cor:', 300, 'Raça/Cor', tipo='select', opcoes=_opcoes_codigo(RACA_COR))
    d.rotulo_com_linha(310, b, 'Telefone:', xf, 'Telefone', fonte='paciente.telefone_contato')
    b += LINHA
    # nome_mae ainda não existe no Paciente (spec §7): fica manual, mas já resolve se o atributo surgir.
    d.rotulo_com_linha(xi, b, 'Nome da Mãe:', xf, 'Nome da Mãe', fonte='paciente.nome_mae')
    b += LINHA
    d.rotulo_com_linha(xi, b, 'Endereço:', xf, 'Endereço')
    b += LINHA
    d.rotulo_com_linha(xi, b, 'Município:', 380, 'Município')
    d.rotulo_com_linha(390, b, 'CEP:', xf, 'CEP')

    # Procedimento Solicitado
    y += altura_secao + 8
    altura_secao = TITULO + 4 * LINHA + 42
    b = secao(y, 'Procedimento Solicitado', altura_secao)
    d.campo('Procedimentos', tipo='procedimentos', obrigatorio=True,
            descricao='Um BPA-I é impresso para cada procedimento marcado.')
    largura_rotulo = d.texto(xi, b, 'Nome do procedimento:', 9)
    d.linha(xi + largura_rotulo + 3, b + 2, xf, b + 2, 0.4)
    d.posicao('Procedimentos', xi + largura_rotulo + 5, b, xf - xi - largura_rotulo - 7, parte='nome')
    b += LINHA
    for rotulo, inicio, fim, parte in (('Cód. Procedimento:', xi, 205, 'codigo'), ('QTD:', 215, 265, 'qtd')):
        largura_rotulo = d.texto(inicio, b, rotulo, 9)
        d.linha(inicio + largura_rotulo + 3, b + 2, fim, b + 2, 0.4)
        d.posicao('Procedimentos', inicio + largura_rotulo + 5, b, fim - inicio - largura_rotulo - 7, parte=parte)
    d.rotulo_com_linha(275, b, 'CID-10:', 365, 'CID-10', descricao='Ex.: H00.1')
    d.rotulo_com_linha(375, b, 'Car. Atend.:', xf, 'Car. Atend.', tipo='select',
                       opcoes=_opcoes_codigo(CARATER_ATENDIMENTO), validacoes={'padrao': '01'})
    b += LINHA
    d.rotulo_com_linha(xi, b, 'Médico solicitante:', xf, 'Médico solicitante', fonte='medico.nome')
    b += LINHA
    d.rotulo_com_linha(xi, b, 'CNS do Profissional:', 300, 'CNS do Profissional (solicitante)', fonte='medico.cns')
    b += 22
    d.linha(330, b, xf - 10, b, 0.6)
    d.texto((330 + xf - 10) / 2, b + 10, 'Ass. e carimbo do Solicitante', 8, alinhamento='center')

    # Justificativa
    y += altura_secao + 8
    altura_secao = TITULO + LINHA + 8
    b = secao(y, 'Justificativa', altura_secao)
    d.rotulo_com_linha(xi, b, 'Hipótese Diagnóstica:', 400, 'Hipótese Diagnóstica')
    d.rotulo_com_linha(410, b, 'CID-10:', xf, 'CID-10 (justificativa)', validacoes={'copiar_de': 'CID-10'},
                       descricao='Em branco, repete o CID-10 do procedimento solicitado.')

    # Resumo do Exame Físico
    y += altura_secao + 8
    altura_secao = 185
    b = secao(y, 'Resumo do Exame Físico', altura_secao)
    d.campo('Resumo do Exame Físico', tipo='textarea', validacoes={'padrao': 'BAV: '})
    d.posicao('Resumo do Exame Físico', xi, b - 4, xf - xi, height=altura_secao - TITULO - 14)

    # Campo reservado para o autorizador (impresso em branco)
    y += altura_secao + 8
    altura_secao = TITULO + LINHA + 40
    b = secao(y, 'CAMPO RESERVADO PARA O AUTORIZADOR', altura_secao)
    d.rotulo_com_linha(xi, b, 'Nº Autorização:', 260)
    d.texto(275, b, 'Data: ______/______/________', 9)
    b += 28
    d.linha(330, b, xf - 10, b, 0.6)
    d.texto((330 + xf - 10) / 2, b + 10, 'Médico Autorizador', 8, alinhamento='center')

    return LayoutGerado(
        nome=NOME,
        descricao='Solicitação de procedimento (BPA-I) de oftalmologia: um formulário por procedimento marcado.',
        arquivo=ARQUIVO,
        pdf=d.finalizar(),
        campos=list(d.campos.values()),
    )
