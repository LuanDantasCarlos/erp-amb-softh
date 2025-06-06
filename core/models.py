"""
Models for the core app.
"""
import os
import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _


class BaseModel(models.Model):
    """Base model with common fields for all models"""
    created_at = models.DateTimeField(_('Data de Criação'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Data de Atualização'), auto_now=True)
    
    class Meta:
        abstract = True


class Paciente(BaseModel):
    """
    Model to store patient information
    """
    SEXO_CHOICES = (
        ('M', _('Masculino')),
        ('F', _('Feminino')),
        ('O', _('Outro')),
    )

    nome = models.CharField(_('Nome Completo'), max_length=255)
    data_nascimento = models.DateField(_('Data de Nascimento'))
    cpf = models.CharField(_('CPF'), max_length=14, unique=True, help_text='Formato: 000.000.000-00')
    rg = models.CharField(_('RG'), max_length=20, blank=True, null=True)
    sexo = models.CharField(_('Sexo'), max_length=1, choices=SEXO_CHOICES)
    telefone = models.CharField(_('Telefone'), max_length=20, blank=True, null=True)
    celular = models.CharField(_('Celular'), max_length=20)
    email = models.EmailField(_('Email'), blank=True, null=True)
    observacoes = models.TextField(_('Observações'), blank=True, null=True)
    ativo = models.BooleanField(_('Ativo'), default=True)

    class Meta:
        verbose_name = _('Paciente')
        verbose_name_plural = _('Pacientes')
        ordering = ['nome']
        indexes = [
            models.Index(fields=['cpf']),
            models.Index(fields=['nome']),
        ]
    
    def __str__(self):
        return f"{self.nome} - {self.cpf}"


class TemplateDocumento(BaseModel):
    """
    Model to store document templates
    """
    nome = models.CharField(_('Nome do Template'), max_length=255)
    descricao = models.TextField(_('Descrição'), blank=True, null=True)
    caminho_template = models.CharField(_('Caminho do Template PDF'), max_length=255)
    criado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name=_('Criado por'))
    ativo = models.BooleanField(_('Ativo'), default=True)
    
    class Meta:
        verbose_name = _('Template de Documento')
        verbose_name_plural = _('Templates de Documentos')
        ordering = ['nome']
    
    def __str__(self):
        return self.nome


def documento_upload_path(instance, filename):
    """
    Define the upload path for documents
    """
    # Get file extension
    ext = filename.split('.')[-1]
    # Create a new filename
    filename = f"{uuid.uuid4()}.{ext}"
    # Return the upload path
    return os.path.join('documentos', str(instance.paciente.id), filename)


class Documento(BaseModel):
    """
    Model to store generated documents
    """
    paciente = models.ForeignKey('Paciente', on_delete=models.CASCADE, related_name='documentos', verbose_name=_('Paciente'))
    template = models.ForeignKey('TemplateDocumento', on_delete=models.SET_NULL, null=True, verbose_name=_('Template'))
    nome = models.CharField(_('Nome do Documento'), max_length=255)
    arquivo = models.FileField(_('Arquivo'), upload_to=documento_upload_path)
    data_emissao = models.DateField(_('Data de Emissão'), auto_now_add=True)
    emitido_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name=_('Emitido por'))
    observacoes = models.TextField(_('Observações'), blank=True, null=True)
    
    class Meta:
        verbose_name = _('Documento')
        verbose_name_plural = _('Documentos')
        ordering = ['-data_emissao']
    
    def __str__(self):
        return f"{self.nome} - {self.paciente}"

    def delete(self, *args, **kwargs):
        """
        Delete the file from the filesystem when the document is deleted
        """
        if self.arquivo:
            if os.path.isfile(self.arquivo.path):
                os.remove(self.arquivo.path)
        super().delete(*args, **kwargs)
