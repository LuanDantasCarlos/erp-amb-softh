"""Engine de overlay: PDF base + valores dos campos nas posições de `CampoTemplateDocumento`.

Compatível com os templates antigos (posicao dict ou lista, atributo sem prefixo). Novidades
(docs/specs/templates-oftalmologia.md §4):
- `procedimentos`: uma cópia do PDF base para cada procedimento marcado;
- checkbox com várias posições por opção (2 vias) e `implica` (marcar OD marca "usar");
- select/radio imprimem o texto da opção, ou "X" nas posições da opção quando ela tiver `posicao`;
- texto com `width` na posição reduz a fonte até `min_font_size` (padrão 7) para caber.

Posição (coordenadas em pontos; `y` medido do topo da página até a linha de base do texto):
`{"x", "y", "width"?, "height"?, "font_size"?, "font_name"?, "align"?: left|center|right,
"min_font_size"?, "pagina"?, "parte"?: nome|codigo|qtd (só procedimentos), "marca"?: "X"}`.

`CampoTemplateDocumento.validacoes` aceita `padrao` (valor inicial) e `copiar_de` (nome de outro campo
cujo valor é usado quando este ficar vazio).
"""
from __future__ import annotations

import io
import json
import logging
from typing import Any, Iterable, Optional

from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from .fontes import ContextoDocumento, resolver_valor

logger = logging.getLogger(__name__)

TIPOS_COM_OPCOES = ('select', 'radio', 'checkbox')
FONTE_PADRAO = 'Helvetica'
TAMANHO_PADRAO = 12
TAMANHO_MINIMO = 7
ENTRELINHA = 1.2


# --- valores ------------------------------------------------------------------------------------

def _vazio(valor: Any) -> bool:
    return valor is None or valor == '' or valor == [] or valor == {}


def _como_lista(valor: Any) -> list:
    if _vazio(valor):
        return []
    if isinstance(valor, (list, tuple)):
        return list(valor)
    if isinstance(valor, str):
        texto = valor.strip()
        if texto.startswith('['):
            try:
                carregado = json.loads(texto)
                if isinstance(carregado, list):
                    return carregado
            except ValueError:
                pass
            try:  # str(list) gravado por versões antigas: "['a', 'b']"
                import ast
                carregado = ast.literal_eval(texto)
                if isinstance(carregado, list):
                    return carregado
            except (ValueError, SyntaxError):
                pass
        return [parte.strip() for parte in texto.split(',') if parte.strip()]
    return [valor]


def posicoes_de(posicao: Any) -> list[dict]:
    if isinstance(posicao, list):
        return [p for p in posicao if isinstance(p, dict)]
    if isinstance(posicao, dict):
        return [posicao]
    return []


def opcoes_normalizadas(campo) -> list[dict]:
    opcoes = []
    for indice, opcao in enumerate(campo.opcoes or []):
        if isinstance(opcao, dict):
            opcoes.append({**opcao, 'id': str(opcao.get('id', indice + 1))})
        else:
            opcoes.append({'id': str(indice + 1), 'texto': str(opcao)})
    return opcoes


def _expandir_implicacoes(campo, marcados: list[str]) -> list[str]:
    resultado = [str(m) for m in marcados]
    for opcao in opcoes_normalizadas(campo):
        if opcao['id'] in resultado:
            for implicada in opcao.get('implica') or []:
                if str(implicada) not in resultado:
                    resultado.append(str(implicada))
    return resultado


def normalizar_procedimentos(valor: Any) -> list[dict]:
    """Lista de {codigo, nome, qtd} na ordem marcada; nome vem do catálogo `Procedimento`."""
    from core.models import Procedimento

    itens = []
    for item in _como_lista(valor):
        if isinstance(item, dict):
            codigo = str(item.get('codigo', '')).strip()
            qtd = item.get('qtd', 1)
        else:
            codigo, qtd = str(item).strip(), 1
        try:
            qtd = max(1, min(99, int(qtd)))
        except (TypeError, ValueError):
            qtd = 1
        if codigo and codigo not in [i['codigo'] for i in itens]:
            itens.append({'codigo': codigo, 'qtd': qtd})
    nomes = dict(Procedimento.objects.filter(codigo__in=[i['codigo'] for i in itens]).values_list('codigo', 'nome'))
    return [{**i, 'nome': nomes.get(i['codigo'], '')} for i in itens if i['codigo'] in nomes]


def valor_automatico(campo, contexto: ContextoDocumento) -> Any:
    """Valor inicial do campo: fonte (`atributo_paciente`) ou, sem fonte, `validacoes.padrao`."""
    valor: Any = resolver_valor(campo.atributo_paciente, contexto) if campo.atributo_paciente else ''
    if _vazio(valor):
        valor = (campo.validacoes or {}).get('padrao', '') if isinstance(campo.validacoes, dict) else ''
    if campo.tipo_campo == 'checkbox':
        return _como_lista(valor)
    return valor


def resolver_valores(
    campos: Iterable,
    campos_valores: dict,
    contexto: ContextoDocumento,
    manter_vazios: Iterable[str] = (),
) -> dict[str, Any]:
    """Valores finais por id do campo. O valor informado sempre vence o automático.

    Campo vazio recebe o automático, a menos que o id esteja em `manter_vazios` (o usuário apagou).
    """
    campos = list(campos)
    manter_vazios = {str(c) for c in manter_vazios}
    campos_valores = campos_valores or {}
    finais: dict[str, Any] = {}

    for campo in campos:
        chave = str(campo.id)
        valor = campos_valores.get(chave)
        if valor is None and campo.nome_campo in campos_valores:
            valor = campos_valores.get(campo.nome_campo)
        if _vazio(valor) and chave not in manter_vazios:
            valor = valor_automatico(campo, contexto)
        if campo.tipo_campo == 'checkbox':
            valor = _expandir_implicacoes(campo, _como_lista(valor))
        elif campo.tipo_campo == 'procedimentos':
            valor = normalizar_procedimentos(valor)
        elif valor is None:
            valor = ''
        finais[chave] = valor

    por_nome = {c.nome_campo: str(c.id) for c in campos}
    for campo in campos:
        origem = (campo.validacoes or {}).get('copiar_de') if isinstance(campo.validacoes, dict) else None
        chave = str(campo.id)
        if origem in por_nome and _vazio(finais[chave]) and chave not in manter_vazios:
            finais[chave] = finais[por_nome[origem]]
    return finais


def valor_para_gravar(valor: Any) -> str:
    """Texto gravado em CampoPreenchidoDocumento (listas e procedimentos em JSON)."""
    if isinstance(valor, (list, dict)):
        return json.dumps(valor, ensure_ascii=False)
    return '' if valor is None else str(valor)


# --- desenho ------------------------------------------------------------------------------------

def _ajustar_fonte(linhas: list[str], fonte: str, tamanho: float, largura: Optional[float], minimo: float) -> float:
    if not largura:
        return tamanho
    while tamanho > minimo and max((stringWidth(l, fonte, tamanho) for l in linhas), default=0) > largura:
        tamanho = max(minimo, tamanho - 0.5)
    return tamanho


def _cortar(linha: str, fonte: str, tamanho: float, largura: Optional[float]) -> str:
    if not largura:
        return linha
    while linha and stringWidth(linha, fonte, tamanho) > largura:
        linha = linha[:-1]
    return linha


def desenhar_texto(can, texto: Any, pos: dict, altura_pagina: float, padrao: Optional[dict] = None) -> None:
    """Texto (uma ou mais linhas) na posição, com auto-ajuste quando `width` estiver definido."""
    texto = '' if texto is None else str(texto)
    if not texto:
        return
    padrao = padrao or {}
    fonte = pos.get('font_name', padrao.get('font_name', FONTE_PADRAO))
    tamanho = float(pos.get('font_size', padrao.get('font_size', TAMANHO_PADRAO)))
    largura = pos.get('width')
    minimo = float(pos.get('min_font_size', TAMANHO_MINIMO))
    linhas = texto.split('\n')
    tamanho = _ajustar_fonte(linhas, fonte, tamanho, largura, min(minimo, tamanho))
    alinhamento = pos.get('align', 'left')
    x = float(pos.get('x', padrao.get('x', 0)))
    y = altura_pagina - float(pos.get('y', padrao.get('y', 0)))
    can.setFont(fonte, tamanho)
    for indice, linha in enumerate(linhas):
        linha = _cortar(linha, fonte, tamanho, largura)
        y_linha = y - indice * tamanho * ENTRELINHA
        if alinhamento == 'center' and largura:
            can.drawCentredString(x + largura / 2, y_linha, linha)
        elif alinhamento == 'right' and largura:
            can.drawRightString(x + largura, y_linha, linha)
        else:
            can.drawString(x, y_linha, linha)


def _desenhar_textarea(can, texto: Any, pos: dict, altura_pagina: float) -> None:
    from core.utils import fit_text_to_box

    fonte = pos.get('font_name', FONTE_PADRAO)
    tamanho = pos.get('font_size', TAMANHO_PADRAO)
    largura = pos.get('width', 300)
    altura = pos.get('height', 60)
    x = pos.get('x', 0)
    y = altura_pagina - pos.get('y', 0)
    can.setFont(fonte, tamanho)
    for indice, linha in enumerate(fit_text_to_box(texto, largura, altura, fonte, tamanho)):
        if indice * tamanho * ENTRELINHA >= altura:
            break
        can.drawString(x, y - indice * tamanho * ENTRELINHA, linha)


def _marcar(can, opcao: dict, pos_campo: dict, altura_pagina: float, pagina: int, pagina_campo: int) -> None:
    """"X" em todas as posições da opção que estão nesta página (sem `pagina`: a do campo)."""
    posicoes = posicoes_de(opcao.get('posicao'))
    if not posicoes:  # legado: opção sem posição própria marca na posição do campo
        posicoes = [pos_campo] if pos_campo else []
    for pos in posicoes:
        if int(pos.get('pagina', pagina_campo)) != pagina:
            continue
        desenhar_texto(can, pos.get('marca', opcao.get('marca', 'X')), pos, altura_pagina, padrao=pos_campo)


def _pagina_de(pos: dict, campo) -> int:
    return int(pos.get('pagina', campo.pagina or 1))


def _desenhar_checkbox(can, campo, valor: Any, altura_pagina: float, pagina: int) -> None:
    """Desenha uma vez por página (as opções têm posições próprias, que podem ser várias)."""
    posicoes = posicoes_de(campo.posicao)
    pagina_campo = _pagina_de(posicoes[0], campo) if posicoes else (campo.pagina or 1)
    pos_campo = next((p for p in posicoes if _pagina_de(p, campo) == pagina), None)
    marcados = [str(v) for v in _como_lista(valor)]
    for opcao in opcoes_normalizadas(campo):
        if opcao['id'] in marcados:
            _marcar(can, opcao, pos_campo or {}, altura_pagina, pagina, pagina_campo)


def _desenhar_campo(can, campo, valor: Any, pos: dict, altura_pagina: float, pagina: int,
                    procedimento: Optional[dict]) -> None:
    tipo = campo.tipo_campo
    if tipo == 'textarea':
        _desenhar_textarea(can, valor, pos, altura_pagina)
    elif tipo in ('select', 'radio'):
        if _vazio(valor):
            return
        opcao = next((o for o in opcoes_normalizadas(campo)
                      if o['id'] == str(valor) or o.get('texto') == str(valor)), None)
        if opcao is None:
            desenhar_texto(can, valor, pos, altura_pagina)
        elif opcao.get('posicao'):
            _marcar(can, opcao, pos, altura_pagina, pagina, _pagina_de(pos, campo))
        else:
            desenhar_texto(can, opcao.get('impressao', opcao.get('texto', '')), pos, altura_pagina)
    elif tipo == 'procedimentos':
        if not procedimento:
            return
        parte = pos.get('parte', 'nome')
        texto = f"{procedimento['qtd']:02d}" if parte == 'qtd' else procedimento.get(parte, '')
        desenhar_texto(can, texto, pos, altura_pagina)
    else:
        desenhar_texto(can, valor, pos, altura_pagina)


def gerar_pdf(template, valores: dict[str, Any]) -> io.BytesIO:
    """Aplica os valores finais (`resolver_valores`) sobre o PDF base do template."""
    with open(template.arquivo_template.path, 'rb') as arquivo:
        base = arquivo.read()

    campos = list(template.campos.all())
    procedimentos: list[dict] = []
    for campo in campos:
        if campo.tipo_campo == 'procedimentos':
            procedimentos = list(valores.get(str(campo.id)) or [])
            break
    repeticoes: list[Optional[dict]] = procedimentos or [None]

    saida = PdfWriter()
    for procedimento in repeticoes:
        leitor = PdfReader(io.BytesIO(base))  # cópia nova da página base a cada repetição
        for indice, pagina in enumerate(leitor.pages):
            numero = indice + 1
            largura = float(pagina.mediabox.width)
            altura = float(pagina.mediabox.height)
            pacote = io.BytesIO()
            can = canvas.Canvas(pacote, pagesize=(largura, altura))
            for campo in campos:
                valor = valores.get(str(campo.id), '')
                if campo.tipo_campo == 'checkbox':
                    _desenhar_checkbox(can, campo, valor, altura, numero)
                    continue
                for pos in posicoes_de(campo.posicao):
                    if _pagina_de(pos, campo) == numero:
                        _desenhar_campo(can, campo, valor, pos, altura, numero, procedimento)
            can.save()
            pacote.seek(0)
            pagina.merge_page(PdfReader(pacote).pages[0])
            saida.add_page(pagina)

    buffer = io.BytesIO()
    saida.write(buffer)
    buffer.seek(0)
    return buffer
