"""
Utility functions for the core app
"""
import os
import io
from django.conf import settings
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from .models import Paciente, TemplateDocumento, CampoTemplateDocumento

def gerar_documento_pdf(paciente, template, campos_valores):
    """
    Generate a PDF document from a template and filled fields.

    Args:
        paciente (Paciente): Patient object
        template (TemplateDocumento): Template object
        campos_valores (dict): Dictionary with field IDs as keys and their values

    Returns:
        io.BytesIO: Buffer containing the generated PDF, or None if an error occurs
    """
    try:
        # Verificar se o template tem um arquivo PDF
        if not template.arquivo_template or not os.path.exists(template.arquivo_template.path):
            return None

        template_path = template.arquivo_template.path
        packet = io.BytesIO()
        can = canvas.Canvas(packet, pagesize=letter)

        for campo in template.campos.all():
            valor = campos_valores.get(str(campo.id), '')

            if not valor and campo.atributo_paciente:
                atributo = campo.atributo_paciente
                valor = getattr(paciente, atributo, '')

            pos = campo.posicao or {}
            x = pos.get('x', 0)
            y = pos.get('y', 0)
            font_size = pos.get('font_size', 12)
            font_name = pos.get('font_name', 'Helvetica')

            can.setFont(font_name, font_size)
            can.drawString(x, y, str(valor or ''))

        can.save()
        packet.seek(0)

        novo_pdf = PdfReader(packet)
        original_pdf = PdfReader(open(template_path, 'rb'))
        output = PdfWriter()

        page = original_pdf.pages[0]
        page.merge_page(novo_pdf.pages[0])
        output.add_page(page)

        final_buffer = io.BytesIO()
        output.write(final_buffer)
        final_buffer.seek(0)

        return final_buffer

    except Exception as e:
        print(f"Erro ao gerar documento: {str(e)}")
        return None
