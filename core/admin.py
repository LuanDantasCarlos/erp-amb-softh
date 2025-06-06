"""
Admin configuration for the core app
"""
from django.contrib import admin
from .models import Paciente, TemplateDocumento, Documento


@admin.register(Paciente)
class PacienteAdmin(admin.ModelAdmin):
    """Admin configuration for Paciente model"""
    list_display = ('nome', 'cpf', 'data_nascimento', 'celular', 'ativo')
    list_filter = ('ativo', 'created_at')
    search_fields = ('nome', 'cpf', 'email', 'celular')
    date_hierarchy = 'created_at'
    fieldsets = (
        ('Informações Pessoais', {
            'fields': (
                'nome', 'data_nascimento', 'cpf', 'rg', 'sexo', 'telefone',
                'celular', 'email'
            )
        }),
        ('Outras Informações', {
            'fields': ('observacoes', 'ativo')
        }),
    )


@admin.register(TemplateDocumento)
class TemplateDocumentoAdmin(admin.ModelAdmin):
    """Admin configuration for TemplateDocumento model"""
    list_display = ('nome', 'criado_por', 'created_at', 'ativo')
    list_filter = ('ativo', 'created_at')
    search_fields = ('nome', 'descricao')
    date_hierarchy = 'created_at'
    fieldsets = (
        ('Informações do Template', {
            'fields': ('nome', 'descricao', 'ativo')
        }),
        ('Conteúdo', {
            'fields': ('conteudo',)
        }),
        ('Metadados', {
            'fields': ('criado_por',),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        """Set the creator if not already set"""
        if not change:  # Only on creation
            if not obj.criado_por:
                obj.criado_por = request.user
        super().save_model(request, obj, form, change)


@admin.register(Documento)
class DocumentoAdmin(admin.ModelAdmin):
    """Admin configuration for Documento model"""
    list_display = ('nome', 'paciente', 'template', 'data_emissao', 'emitido_por')
    list_filter = ('data_emissao', 'template')
    search_fields = ('nome', 'paciente__nome', 'observacoes')
    date_hierarchy = 'data_emissao'
    readonly_fields = ('arquivo',)
    
    fieldsets = (
        ('Informações do Documento', {
            'fields': ('nome', 'paciente', 'template', 'arquivo')
        }),
        ('Metadados', {
            'fields': ('data_emissao', 'emitido_por', 'observacoes')
        }),
    )
    
    def save_model(self, request, obj, form, change):
        """Set the issuer if not already set"""
        if not change:  # Only on creation
            if not obj.emitido_por:
                obj.emitido_por = request.user
        super().save_model(request, obj, form, change)
