"""Prescrição de Óculos (A4 retrato). Spec §5.2."""
from __future__ import annotations

from reportlab.lib.pagesizes import A4

from .base import Desenho, LayoutGerado

NOME = 'Prescrição de Óculos'
ARQUIVO = 'prescricao_oculos.pdf'

COLUNAS = (('OLHO', 110), ('ESFÉRICO', 120), ('CILINDRO', 120), ('EIXO', 100))
OLHOS = (('Direito', 'OD'), ('Esquerdo', 'OE'))
ALTURA_LINHA = 24


def _tabela(d: Desenho, titulo: str, y: float) -> float:
    largura_total = sum(w for _, w in COLUNAS)
    x_inicio = (d.largura - largura_total) / 2
    d.texto(x_inicio, y, titulo, 12, negrito=True)
    topo = y + 10
    for linha in range(3):
        y_linha = topo + linha * ALTURA_LINHA
        x = x_inicio
        for indice, (coluna, largura) in enumerate(COLUNAS):
            d.retangulo(x, y_linha, largura, ALTURA_LINHA, 0.7)
            base = y_linha + 16
            if linha == 0:
                d.texto(x + largura / 2, base, coluna, 10, negrito=True, alinhamento='center')
            elif indice == 0:
                d.texto(x + largura / 2, base, OLHOS[linha - 1][0], 10, alinhamento='center')
            else:
                nome = f'{titulo.capitalize()} {OLHOS[linha - 1][1]} {coluna.capitalize()}'
                d.campo(nome)
                d.posicao(nome, x + 4, base, largura - 8, tamanho=11, alinhamento='center')
            x += largura
    return topo + 3 * ALTURA_LINHA


def construir() -> LayoutGerado:
    largura, altura = A4
    d = Desenho(largura, altura)
    centro = largura / 2
    x0, x1 = 60, largura - 60

    altura_logo = d.imagem('logo_governo_es.jpeg', centro - 85, 36, 170)  # ~6 cm
    y = 36 + altura_logo + 22
    for nome, fonte in (('Núcleo', 'estabelecimento.nucleo'), ('Unidade', 'estabelecimento.unidade')):
        d.campo(nome, fonte=fonte)
        d.posicao(nome, x0, y, x1 - x0, tamanho=12, negrito=True, alinhamento='center')
        y += 18
    y += 8
    d.texto(centro, y, 'PRESCRIÇÃO DE ÓCULOS', 13, negrito=True, alinhamento='center')

    y += 34
    pos = d.rotulo_com_linha(x0, y, 'Nome:', x1, 'Nome', tamanho=11, negrito=True, fonte='paciente.nome',
                             obrigatorio=True)
    pos['font_size'] = 11

    y = _tabela(d, 'LONGE', y + 36)
    y = _tabela(d, 'PERTO', y + 32)

    y += 36
    pos = d.rotulo_com_linha(x0, y, 'ADD: +', 220, 'ADD', tamanho=11, negrito=True)
    pos['font_size'] = 11
    y += 30
    pos = d.rotulo_com_linha(x0, y, 'Data do Atendimento:', 300, 'Data do Atendimento', tamanho=11, negrito=True,
                             fonte='atendimento.data')
    pos['font_size'] = 11

    y += 90
    d.linha(centro - 140, y, centro + 140, y, 0.7)
    d.campo('Assinatura', fonte='medico.assinatura', descricao='Dr(a). nome e CRM do médico.')
    d.posicao('Assinatura', centro - 160, y + 16, 320, tamanho=11, negrito=True, alinhamento='center')
    d.campo('Especialidade', fonte='medico.especialidade_exibicao')
    d.posicao('Especialidade', centro - 160, y + 16 + 2 * 13.2 + 2, 320, tamanho=11, negrito=True, alinhamento='center')

    return LayoutGerado(
        nome=NOME,
        descricao='Prescrição de óculos (longe/perto, OD/OE) com assinatura do médico.',
        arquivo=ARQUIVO,
        pdf=d.finalizar(),
        campos=list(d.campos.values()),
    )
