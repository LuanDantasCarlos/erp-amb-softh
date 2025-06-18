import io
import os
from datetime import datetime
from django.conf import settings
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from .models import Documento, Paciente, TemplateDocumento, CampoPreenchidoDocumento, CampoTemplateDocumento
from .serializers import DocumentoSerializer, GerarDocumentoSerializer, TemplateDocumentoSerializer, CampoTemplateDocumentoSerializer, PacienteSerializer
from .utils import gerar_documento_pdf

class PacienteViewSet(viewsets.ModelViewSet):
    queryset = Paciente.objects.all()
    serializer_class = PacienteSerializer

class TemplateDocumentoViewSet(viewsets.ModelViewSet):
    queryset = TemplateDocumento.objects.all()
    serializer_class = TemplateDocumentoSerializer

    def perform_create(self, serializer):
        serializer.save(criado_por=self.request.user)

class CampoTemplateDocumentoViewSet(viewsets.ModelViewSet):
    queryset = CampoTemplateDocumento.objects.all()
    serializer_class = CampoTemplateDocumentoSerializer

class DocumentoViewSet(viewsets.ModelViewSet):
    queryset = Documento.objects.all()
    serializer_class = DocumentoSerializer

    def get_queryset(self):
        return Documento.objects.all().order_by("-created_at")

    @action(detail=False, methods=['post'])
    def gerar(self, request):
        """
        Gera um documento PDF baseado em um template existente, preenchendo os campos dinamicamente.
        """
        serializer = GerarDocumentoSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        paciente = get_object_or_404(Paciente, id=serializer.validated_data['paciente_id'])
        template_doc = get_object_or_404(TemplateDocumento, id=serializer.validated_data['template_id'])
        nome_documento = serializer.validated_data['nome_documento']
        observacoes = serializer.validated_data.get('observacoes', '')
        campos_valores = serializer.validated_data['campos']

        try:
            # Validar campos obrigatórios e tipos
            for campo in template_doc.campos.all():
                valor = campos_valores.get(campo.nome_campo)
                if campo.obrigatorio and (valor is None or str(valor).strip() == ''):
                    return Response(
                        {"error": f"O campo obrigatório '{campo.nome_campo}' não foi preenchido."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                if valor:
                    if campo.tipo_campo == 'number':
                        try:
                            float(valor)
                        except (ValueError, TypeError):
                            return Response(
                                {"error": f"O campo '{campo.nome_campo}' deve ser um número."},
                                status=status.HTTP_400_BAD_REQUEST
                            )
                    elif campo.tipo_campo == 'date':
                        try:
                            datetime.strptime(valor, '%d/%m/%Y')  # Ajuste o formato conforme seu padrão
                        except (ValueError, TypeError):
                            return Response(
                                {"error": f"O campo '{campo.nome_campo}' deve ser uma data no formato DD/MM/AAAA."},
                                status=status.HTTP_400_BAD_REQUEST
                            )
                    elif campo.tipo_campo == 'boolean':
                        if str(valor) not in ['True', 'False', 'Sim', 'Não']:
                            return Response(
                                {"error": f"O campo '{campo.nome_campo}' deve ser 'Sim' ou 'Não'."},
                                status=status.HTTP_400_BAD_REQUEST
                            )

            # Criar o documento
            documento = Documento.objects.create(
                paciente=paciente,
                template=template_doc,
                nome=nome_documento,
                emitido_por=request.user,
                observacoes=observacoes,
            )
            documento.registrar_acao(request.user, "gerado")

            # Salvar os campos preenchidos
            for campo in template_doc.campos.all():
                valor = campos_valores.get(campo.nome_campo, '')
                CampoPreenchidoDocumento.objects.create(
                    documento=documento,
                    campo_template=campo,
                    valor=valor
                )

            # Gerar o PDF
            pdf_buffer = gerar_documento_pdf(paciente, template_doc, campos_valores)
            if pdf_buffer:
                return FileResponse(
                    pdf_buffer,
                    as_attachment=True,
                    filename=f"{nome_documento}.pdf",
                    content_type='application/pdf'
                )
            else:
                documento.delete()
                return Response({"error": "Erro ao gerar o PDF."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as e:
            import traceback
            return Response({
                "error": str(e),
                "traceback": traceback.format_exc()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """
        Regenera e faz o download do PDF de um documento existente.
        """
        documento = self.get_object()
        template = documento.template
        paciente = documento.paciente
        campos_valores = {cp.campo_template.nome_campo: cp.valor for cp in documento.campos_preenchidos.all()}

        pdf_buffer = gerar_documento_pdf(paciente, template, campos_valores)
        if pdf_buffer:
            documento.registrar_acao(request.user, "download")
            return FileResponse(
                pdf_buffer,
                as_attachment=True,
                filename=f"{documento.nome}.pdf",
                content_type='application/pdf'
            )
        return Response({"error": "Erro ao gerar o PDF."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def destroy(self, request, *args, **kwargs):
        documento = self.get_object()
        documento.registrar_acao(request.user, "excluído")
        return super().destroy(request, *args, **kwargs)