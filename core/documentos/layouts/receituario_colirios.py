"""Receituário de Colírios: A4 paisagem, 2 vias lado a lado. Spec §5.3."""
from __future__ import annotations

from reportlab.lib.pagesizes import A4, landscape

from .base import LADO_CAIXA, Desenho, LayoutGerado

NOME = 'Receituário de Colírios (2 vias)'
ARQUIVO = 'receituario_colirios_2vias.pdf'
NOME_ANTIGO = 'Receituario Colirio - Timolol'

MEDICAMENTOS = (
    ('Maleato de Timolol 0,5%', 'Pingar 01 (uma) gota de 12/12hs (07:00 e 19:00hs)'),
    ('Travoprosta 0,004%', 'Pingar 01 (uma) gota às 20:00hs (todas as noites)'),
    ('Bimatoprosta 0,03%', 'Pingar 01 (uma) gota às 20:00hs (todas as noites)'),
    ('Latanoprosta 0,005%', 'Pingar 01 (uma) gota às 20:00hs (todas as noites)'),
    ('Tartarato de Brimonidina 0,2%', 'Pingar 01 (uma) gota de 12/12hs (07:30 e 19:30hs)'),
    ('Dorzolamida 2%', 'Pingar 01 (uma) gota de 12/12hs (07:45 e 19:45hs)'),
    ('Brinzolamida 1%', 'Pingar 01 (uma) gota de 12/12hs (07:45 e 19:45hs)'),
)
QUANTIDADE = '1 frasco/mês'
ORAL = 'Acetazolamida comprimido 250mg'
MARGEM_VIA = 20
PASSO_ITEM = 34


def nome_campo_medicamento(indice: int, medicamento: str) -> str:
    return f'{indice}. {medicamento}'


def _pontilhado(d: Desenho, x1: float, x2: float, y: float) -> None:
    d.c.setDash(1, 2)
    d.linha(x1, y, x2, y, 0.5)
    d.c.setDash()


def _via(d: Desenho, ox: float, largura_via: float, caixas: dict) -> None:
    xa, xb = ox + MARGEM_VIA, ox + largura_via - MARGEM_VIA

    altura_faixa = d.imagem('cabecalho_sus_es.png', xa, 14, 245)
    x_caixa = xa + 253
    d.retangulo(x_caixa, 14, xb - x_caixa, altura_faixa, 0.9)
    d.texto((x_caixa + xb) / 2, 14 + altura_faixa / 2 + 4, 'RECEITUÁRIO', 12, negrito=True, alinhamento='center')

    y = 14 + altura_faixa + 20
    largura_rotulo = d.texto(xa, y, 'UNIDADE DE SAÚDE:', 9, negrito=True)
    d.campo('Unidade de saúde', fonte='estabelecimento.nome')
    d.posicao('Unidade de saúde', xa + largura_rotulo + 4, y, xb - xa - largura_rotulo - 4, tamanho=9, negrito=True)
    y += 20
    d.rotulo_com_linha(xa, y, 'NOME:', xb, 'Nome', negrito=True, fonte='paciente.nome', obrigatorio=True)
    d.campos['Nome'].posicoes[-1]['font_size'] = 9.5
    y += 21
    d.texto(xa, y, 'USO OCULAR:', 9, negrito=True)

    y += 16
    for indice, (medicamento, posologia) in enumerate(MEDICAMENTOS, start=1):
        nome = nome_campo_medicamento(indice, medicamento)
        d.texto(xa, y, f'{indice}.', 8.5, negrito=True)
        caixas.setdefault((nome, 'usar'), []).append(d.caixa_marcacao(xa + 13, y))
        largura_texto = d.texto(xa + 13 + LADO_CAIXA + 5, y, medicamento, 8.5, negrito=True)
        largura_qtd = d.texto(xb, y, QUANTIDADE, 8.5, alinhamento='right')
        _pontilhado(d, xa + 13 + LADO_CAIXA + 5 + largura_texto + 4, xb - largura_qtd - 4, y)
        y2 = y + 11
        caixas.setdefault((nome, 'od'), []).append(d.caixa_marcacao(xa + 26, y2))
        d.texto(xa + 26 + LADO_CAIXA + 4, y2, 'Olho Direito', 8)
        caixas.setdefault((nome, 'oe'), []).append(d.caixa_marcacao(xa + 110, y2))
        d.texto(xa + 110 + LADO_CAIXA + 4, y2, 'Olho Esquerdo', 8)
        d.texto(xa + 26, y + 22, posologia, 8)
        y += PASSO_ITEM

    y += 2
    d.texto(xa, y, 'USO ORAL:', 9, negrito=True)
    y += 15
    nome_oral = nome_campo_medicamento(len(MEDICAMENTOS) + 1, ORAL)
    d.texto(xa, y, f'{len(MEDICAMENTOS) + 1}.', 8.5, negrito=True)
    caixas.setdefault((nome_oral, 'usar'), []).append(d.caixa_marcacao(xa + 13, y))
    d.texto(xa + 13 + LADO_CAIXA + 5, y, ORAL, 8.5, negrito=True)
    y += 15
    d.campo('Acetazolamida - quantidade/posologia', descricao='Texto livre (não há posologia padrão).')
    d.linha(xa + 26, y + 2, xb, y + 2, 0.4)
    d.posicao('Acetazolamida - quantidade/posologia', xa + 28, y, xb - xa - 30, tamanho=8.5)

    y += 28
    largura_rotulo = d.texto(xa, y, 'DATA:', 9, negrito=True)
    d.campo('Data', fonte='atendimento.data')
    d.posicao('Data', xa + largura_rotulo + 4, y, 120, tamanho=9, negrito=True)

    centro = (xa + xb) / 2
    y += 46
    d.linha(centro - 120, y, centro + 120, y, 0.7)
    d.campo('Assinatura', fonte='medico.assinatura', descricao='Dr(a). nome e CRM do médico.')
    d.posicao('Assinatura', centro - 150, y + 13, 300, tamanho=9, negrito=True, alinhamento='center')
    d.campo('Especialidade', fonte='medico.especialidade_exibicao')
    d.posicao('Especialidade', centro - 150, y + 13 + 2 * 9 * 1.2 + 1, 300, tamanho=9, negrito=True,
              alinhamento='center')
    d.texto(centro, y + 62, 'Ao voltar à consulta traga esta receita', 8.5, negrito=True, alinhamento='center')


def construir() -> LayoutGerado:
    largura, altura = landscape(A4)
    d = Desenho(largura, altura)
    largura_via = largura / 2
    caixas: dict = {}

    # Campos na ordem do formulário: cabeçalho e medicamentos antes dos campos do rodapé.
    for indice, (medicamento, _) in enumerate(MEDICAMENTOS, start=1):
        d.campo(nome_campo_medicamento(indice, medicamento), tipo='checkbox')
    d.campo(nome_campo_medicamento(len(MEDICAMENTOS) + 1, ORAL), tipo='checkbox')

    for ox in (0, largura_via):
        _via(d, ox, largura_via, caixas)
    d.c.setDash(4, 3)
    d.linha(largura_via, 10, largura_via, altura - 10, 0.5)
    d.c.setDash()

    for indice, (medicamento, _) in enumerate(MEDICAMENTOS, start=1):
        nome = nome_campo_medicamento(indice, medicamento)
        campo = d.campos[nome]
        campo.opcoes = [
            {'id': 'usar', 'texto': 'Usar', 'posicao': caixas[(nome, 'usar')]},
            {'id': 'od', 'texto': 'Olho Direito', 'posicao': caixas[(nome, 'od')], 'implica': ['usar']},
            {'id': 'oe', 'texto': 'Olho Esquerdo', 'posicao': caixas[(nome, 'oe')], 'implica': ['usar']},
        ]
        campo.posicoes = [dict(caixas[(nome, 'usar')][0])]
        campo.descricao = 'Marcar OD ou OE marca o medicamento.'
    nome_oral = nome_campo_medicamento(len(MEDICAMENTOS) + 1, ORAL)
    d.campos[nome_oral].opcoes = [{'id': 'usar', 'texto': 'Usar', 'posicao': caixas[(nome_oral, 'usar')]}]
    d.campos[nome_oral].posicoes = [dict(caixas[(nome_oral, 'usar')][0])]

    primeiros = ('Unidade de saúde', 'Nome')
    campos = [d.campos[n] for n in primeiros] + [c for n, c in d.campos.items() if n not in primeiros]

    return LayoutGerado(
        nome=NOME,
        descricao='Receituário de colírios para glaucoma, 2 vias lado a lado (A4 paisagem).',
        arquivo=ARQUIVO,
        pdf=d.finalizar(),
        campos=campos,
    )

