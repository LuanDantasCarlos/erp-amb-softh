"""
Utility functions for the core app
"""
import os
import uuid
from django.conf import settings
from django.template import Template, Context
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph
from .models import Paciente, TemplateDocumento


def gerar_documento_pdf(paciente_id, template_id, nome_documento):
    """
    Generate a PDF document from a template and patient data
    
    Args:
        paciente_id (int): Patient ID
        template_id (int): Template ID
        nome_documento (str): Document name
        
    Returns:
        tuple: (success, result)
            - If success is True, result is the path to the generated PDF file
            - If success is False, result is the error message
    """
    try:
        # Get patient and template
        paciente = Paciente.objects.get(id=paciente_id)
        template_doc = TemplateDocumento.objects.get(id=template_id)
        
        # Render template with patient data
        template = Template(template_doc.conteudo)
        context = Context({
            'paciente': paciente
        })
        content = template.render(context)
        
        # Create document storage directory if it doesn't exist
        os.makedirs(settings.DOCUMENT_STORAGE_PATH, exist_ok=True)
        paciente_dir = os.path.join(settings.DOCUMENT_STORAGE_PATH, str(paciente.id))
        os.makedirs(paciente_dir, exist_ok=True)
        
        # Generate a unique filename
        filename = f"{nome_documento.replace(' ', '_')}_{uuid.uuid4().hex[:8]}.pdf"
        file_path = os.path.join(paciente_dir, filename)
        
        # Create PDF with ReportLab
        styles = getSampleStyleSheet()
        doc = SimpleDocTemplate(file_path, pagesize=letter)
        
        # Split the content by lines for easier formatting
        paragraphs = []
        for line in content.split('\n'):
            if line.strip():  # Avoid empty lines
                para = Paragraph(line, styles['Normal'])
                paragraphs.append(para)
        
        # Build the PDF document
        doc.build(paragraphs)
        
        # Return the relative path to be stored in the database
        return True, f"documentos/{paciente.id}/{filename}"
        
    except Paciente.DoesNotExist:
        return False, "Paciente não encontrado."
    except TemplateDocumento.DoesNotExist:
        return False, "Template não encontrado."
    except Exception as e:
        return False, f"Erro ao gerar documento: {str(e)}"
