"""
Admin configuration for the core app
"""
from django.contrib import admin
from .models import Agendamento, Documento, ExecucaoImportacao, Paciente, TemplateDocumento


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
        ('Soul MV', {
            'fields': ('codigo_cidadao', 'cns', 'nome_social', 'origem'),
            'classes': ('collapse',)
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


@admin.register(Agendamento)
class AgendamentoAdmin(admin.ModelAdmin):
    list_display = ('solicitacao', 'paciente', 'item_agendamento', 'data_agenda', 'created_at')
    list_filter = ('data_agenda', 'created_at')
    search_fields = ('solicitacao', 'paciente__nome', 'paciente__codigo_cidadao', 'item_agendamento')
    date_hierarchy = 'data_agenda'
    raw_id_fields = ('paciente',)
    list_select_related = ('paciente',)


@admin.register(ExecucaoImportacao)
class ExecucaoImportacaoAdmin(admin.ModelAdmin):
    """Somente leitura: monitoramento do job de importação Soul MV."""
    list_display = (
        'iniciado_em', 'finalizado_em', 'status', 'linhas_lidas', 'pacientes_criados',
        'agendamentos_criados', 'linhas_rejeitadas', 'arquivo',
    )
    list_filter = ('status', 'iniciado_em')
    date_hierarchy = 'iniciado_em'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
