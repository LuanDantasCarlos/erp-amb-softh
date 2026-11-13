import io
import logging
import os
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics

logger = logging.getLogger(__name__)

def fit_text_to_box(text, width_pt, height_pt, font_name, font_size):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    line_height = font_size * 1.2
    max_lines = int(height_pt // line_height)
    lines = []
    if not text:
        return lines

    paragraphs = str(text).split('\n')
    for paragraph in paragraphs:
        words = paragraph.split()
        current_line = ""
        for word in words:
            # Se palavra longa demais, força quebra
            if stringWidth(word, font_name, font_size) > width_pt:
                # Quebra a palavra em pedaços menores
                for i in range(0, len(word), 1):
                    part = word[i:i+1]
                    test_line = (current_line + part).strip()
                    if stringWidth(test_line, font_name, font_size) <= width_pt:
                        current_line = test_line
                    else:
                        if current_line:
                            lines.append(current_line)
                        current_line = part
                        if len(lines) >= max_lines:
                            break
                continue
            test_line = (current_line + " " + word).strip()
            if stringWidth(test_line, font_name, font_size) <= width_pt:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
                if len(lines) >= max_lines:
                    break
        if current_line and len(lines) < max_lines:
            lines.append(current_line)
        if len(lines) >= max_lines:
            break
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    return lines

def calcular_maxchars_textarea(width_pt, height_pt, font_name="Helvetica", font_size=12):
    texto_teste = "a" * 2000  # Texto contínuo, sem espaços
    for i in range(1, len(texto_teste)):
        test_text = texto_teste[:i]
        linhas = fit_text_to_box(test_text, width_pt, height_pt, font_name, font_size)
        total_rendered = sum(len(l) for l in linhas)
        if total_rendered < i:
            return i - 1
    return len(texto_teste)

def gerar_documento_pdf(paciente, template, campos_valores, contexto=None, manter_vazios=()):
    """Gera o PDF do template (core.documentos.engine). Devolve BytesIO ou None em caso de erro.

    Sem `contexto`, só o paciente alimenta os campos automáticos (comportamento dos templates antigos).
    """
    from core.documentos.engine import gerar_pdf, resolver_valores
    from core.documentos.fontes import ContextoDocumento

    try:
        if not template.arquivo_template or not os.path.exists(template.arquivo_template.path):
            logger.warning('Template %s sem arquivo PDF base.', template.pk)
            return None
        if contexto is None:
            contexto = ContextoDocumento(paciente=paciente)
        valores = resolver_valores(template.campos.all(), campos_valores or {}, contexto, manter_vazios)
        return gerar_pdf(template, valores)
    except Exception:
        logger.exception('Erro ao gerar documento do template %s', getattr(template, 'pk', None))
        return None
