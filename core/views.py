"""
Views for the core app
"""
import os
import tempfile
import io
from django.http import HttpResponse, FileResponse
from django.template import Template, Context
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.contrib.auth.models import User
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph
from rest_framework.views import APIView
from PyPDF2 import PdfReader, PdfWriter

from .models import Paciente, TemplateDocumento, Documento
from .serializers import (
    PacienteSerializer, 
    TemplateDocumentoSerializer, 
    DocumentoSerializer,
    GerarDocumentoSerializer,
)


class PacienteViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing patients
    """
    queryset = Paciente.objects.all()
    serializer_class = PacienteSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['ativo', 'cidade', 'estado']
    search_fields = ['nome', 'cpf', 'email', 'celular']
    ordering_fields = ['nome', 'created_at', 'data_nascimento']
    ordering = ['nome']
    
    @action(detail=True, methods=['get'])
    def documentos(self, request, pk=None):
        """
        List all documents for a patient
        """
        paciente = self.get_object()
        documentos = Documento.objects.filter(paciente=paciente)
        serializer = DocumentoSerializer(documentos, many=True)
        return Response(serializer.data)


class TemplateDocumentoViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing document templates
    """
    queryset = TemplateDocumento.objects.all()
    serializer_class = TemplateDocumentoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['ativo']
    search_fields = ['nome', 'descricao']
    ordering_fields = ['nome', 'created_at']
    ordering = ['nome']
    
    def perform_create(self, serializer):
        serializer.save(criado_por=self.request.user)


class DocumentoViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing documents
    """
    queryset = Documento.objects.all()
    serializer_class = DocumentoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['paciente', 'template']
    search_fields = ['nome', 'observacoes']
    ordering_fields = ['nome', 'created_at', 'data_emissao']
    ordering = ['-data_emissao']
    
    def perform_create(self, serializer):
        serializer.save(emitido_por=self.request.user)
    
    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """
        Download a document
        """
        documento = self.get_object()
        if not documento.arquivo:
            return Response(
                {"error": "Arquivo não encontrado."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Provide the document as a FileResponse
        try:
            return FileResponse(
                open(documento.arquivo.path, 'rb'),
                as_attachment=True,
                filename=os.path.basename(documento.arquivo.name)
            )
        except Exception as e:
            return Response(
                {"error": f"Erro ao baixar o arquivo: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def gerar(self, request):
        """
        Generate a document based on a template and patient data
        """
        serializer = GerarDocumentoSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # Get patient and template
        paciente = get_object_or_404(Paciente, id=serializer.validated_data['paciente_id'])
        template_doc = get_object_or_404(TemplateDocumento, id=serializer.validated_data['template_id'])
        
        # Process template content
        try:
            # Render Django template with patient data
            django_template = Template(template_doc.conteudo)
            context = Context({
                'paciente': paciente
            })
            content = django_template.render(context)
            
            # Create directories for document storage
            os.makedirs(settings.DOCUMENT_STORAGE_PATH, exist_ok=True)
            paciente_dir = os.path.join(settings.DOCUMENT_STORAGE_PATH, str(paciente.id))
            os.makedirs(paciente_dir, exist_ok=True)
            
            # Create filename for the PDF
            nome_documento = serializer.validated_data['nome_documento']
            observacoes = serializer.validated_data.get('observacoes', '')
            filename = f"{nome_documento.replace(' ', '_')}_{paciente.id}.pdf"
            final_path = os.path.join(paciente_dir, filename)
            
            # Create PDF with ReportLab
            styles = getSampleStyleSheet()
            doc = SimpleDocTemplate(final_path, pagesize=letter)
            
            # Split the content by lines for easier formatting
            paragraphs = []
            for line in content.split('\n'):
                if line.strip():  # Avoid empty lines
                    para = Paragraph(line, styles['Normal'])
                    paragraphs.append(para)
            
            # Build the PDF document
            doc.build(paragraphs)
            
            # Create document object in database
            document_path = f"documentos/{paciente.id}/{filename}"
            documento = Documento.objects.create(
                paciente=paciente,
                template=template_doc,
                nome=nome_documento,
                arquivo=document_path,
                emitido_por=request.user,
                observacoes=observacoes
            )
            
            # Return the created document
            return Response(
                DocumentoSerializer(documento).data,
                status=status.HTTP_201_CREATED
            )
                
        except Exception as e:
            import traceback
            return Response(
                {
                    "error": f"Erro ao gerar documento: {str(e)}",
                    "traceback": traceback.format_exc()
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )





class GerarPrescricaoPDFView(APIView):
    permission_classes = []

    def get(self, request, *args, **kwargs):
        
        nome = "João da Silva"
        od_longe = "-1.25"
        oe_longe = "-1.00"
        od_perto = "-0.75"
        oe_perto = "-0.50"
        data_prescricao = "23-05-2025"

        pdf_base_path = os.path.join("static", "templates_documentos", "PRESCRIÇAO OCULOS.pdf")

        packet = io.BytesIO()
        can = canvas.Canvas(packet)
        can.setFont("Helvetica", 12)

        # OBS: Ajuste fino pode ser necessário com base em visualização real do PDF

        # Nome (linha abaixo do "Nome:")
        can.drawString(140, 510, nome)

        # Longe
        can.drawString(200, 400, od_longe)  # Olho Direito
        can.drawString(200, 385, oe_longe)  # Olho Esquerdo

        # Perto
        can.drawString(200, 335, od_perto)  # Olho Direito
        can.drawString(200, 315, oe_perto)  # Olho Esquerdo

        # Data
        #can.drawString(100, 450, data_prescricao)

        can.save()

        packet.seek(0)
        novo_pdf = PdfReader(packet)
        original_pdf = PdfReader(open(pdf_base_path, "rb"))
        output = PdfWriter()

        page = original_pdf.pages[0]
        page.merge_page(novo_pdf.pages[0])
        output.add_page(page)

        resultado = io.BytesIO()
        output.write(resultado)
        resultado.seek(0)

        return FileResponse(resultado, as_attachment=True, filename="prescricao_oculos.pdf")
