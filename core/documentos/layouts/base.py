"""Base dos layouts gerados por código: desenha o PDF base e registra as posições dos campos.

Coordenadas em pontos, com `y` medido a partir do TOPO da página (mesma convenção da engine:
`y` é a linha de base do texto). Desenho e posição saem do mesmo cálculo, então batem exatamente.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

ASSETS = Path(__file__).resolve().parent.parent / 'assets'
FONTE = 'Helvetica'
FONTE_NEGRITO = 'Helvetica-Bold'
TAMANHO_CAMPO = 10
LADO_CAIXA = 8  # quadrado de "[ ]"


@dataclass
class CampoLayout:
    """Definição de um CampoTemplateDocumento (upsert por `nome`)."""

    nome: str
    tipo: str = 'text'
    fonte: Optional[str] = None  # atributo_paciente (com prefixo de fonte)
    posicoes: list[dict] = field(default_factory=list)
    opcoes: Optional[list[dict]] = None
    obrigatorio: bool = False
    descricao: Optional[str] = None
    validacoes: Optional[dict] = None

    @property
    def posicao(self) -> Any:
        """Uma posição vira dict (formato antigo); várias, lista."""
        return self.posicoes[0] if len(self.posicoes) == 1 else list(self.posicoes)


@dataclass
class LayoutGerado:
    nome: str
    descricao: str
    arquivo: str  # nome do PDF base em MEDIA_ROOT/templates/oftalmologia/
    pdf: bytes
    campos: list[CampoLayout]


class Desenho:
    """Canvas do reportlab com origem no topo e registro de campos."""

    def __init__(self, largura: float, altura: float) -> None:
        self.largura = largura
        self.altura = altura
        self.buffer = io.BytesIO()
        self.c = canvas.Canvas(self.buffer, pagesize=(largura, altura))
        self.c.setLineWidth(0.6)
        self.campos: dict[str, CampoLayout] = {}

    # --- primitivas (y a partir do topo) ----------------------------------------------------------

    def texto(self, x: float, y: float, s: str, tamanho: float = 9, negrito: bool = False,
              alinhamento: str = 'left') -> float:
        fonte = FONTE_NEGRITO if negrito else FONTE
        self.c.setFont(fonte, tamanho)
        yy = self.altura - y
        if alinhamento == 'center':
            self.c.drawCentredString(x, yy, s)
        elif alinhamento == 'right':
            self.c.drawRightString(x, yy, s)
        else:
            self.c.drawString(x, yy, s)
        return stringWidth(s, fonte, tamanho)

    def linha(self, x1: float, y1: float, x2: float, y2: float, espessura: float = 0.6) -> None:
        self.c.setLineWidth(espessura)
        self.c.line(x1, self.altura - y1, x2, self.altura - y2)

    def retangulo(self, x: float, y: float, w: float, h: float, espessura: float = 0.8) -> None:
        self.c.setLineWidth(espessura)
        self.c.rect(x, self.altura - y - h, w, h, stroke=1, fill=0)

    def imagem(self, nome: str, x: float, y: float, largura: float) -> float:
        """Imagem do diretório de assets com a largura dada; devolve a altura usada."""
        leitor = ImageReader(str(ASSETS / nome))
        w, h = leitor.getSize()
        altura = largura * h / w
        self.c.drawImage(leitor, x, self.altura - y - altura, width=largura, height=altura, mask='auto')
        return altura

    # --- campos ----------------------------------------------------------------------------------

    def campo(self, nome: str, **kwargs: Any) -> CampoLayout:
        if nome not in self.campos:
            self.campos[nome] = CampoLayout(nome=nome, **kwargs)
        return self.campos[nome]

    def posicao(self, nome: str, x: float, y: float, largura: Optional[float] = None, tamanho: float = TAMANHO_CAMPO,
                negrito: bool = False, alinhamento: str = 'left', **extra: Any) -> dict:
        pos: dict[str, Any] = {'x': round(x, 2), 'y': round(y, 2), 'font_size': tamanho, 'pagina': 1}
        if largura:
            pos['width'] = round(largura, 2)
        if negrito:
            pos['font_name'] = FONTE_NEGRITO
        if alinhamento != 'left':
            pos['align'] = alinhamento
        pos.update(extra)
        self.campos[nome].posicoes.append(pos)
        return pos

    def rotulo_com_linha(self, x: float, y: float, rotulo: str, x_fim: float, nome: Optional[str] = None,
                         tamanho: float = 9, negrito: bool = False, **campo: Any) -> Optional[dict]:
        """`Rótulo: ________` até x_fim; registra o campo (se `nome`) sobre a linha."""
        largura_rotulo = self.texto(x, y, rotulo, tamanho, negrito)
        inicio = x + largura_rotulo + 3
        self.linha(inicio, y + 2, x_fim, y + 2, 0.4)
        if nome is None:
            return None
        self.campo(nome, **campo)
        return self.posicao(nome, inicio + 2, y, x_fim - inicio - 4)

    def caixa_marcacao(self, x: float, y: float) -> dict:
        """Quadrado de "[ ]" com a base na linha y; devolve a posição do "X" centralizado nele."""
        self.retangulo(x, y - LADO_CAIXA + 1, LADO_CAIXA, LADO_CAIXA, 0.6)
        return {'x': round(x, 2), 'y': round(y - 0.4, 2), 'width': LADO_CAIXA, 'align': 'center',
                'font_size': 8, 'font_name': FONTE_NEGRITO, 'pagina': 1}

    def finalizar(self) -> bytes:
        self.c.showPage()
        self.c.save()
        return self.buffer.getvalue()
