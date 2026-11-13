import os
import uuid
import pytz
from datetime import datetime
from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
from django.core.validators import FileExtensionValidator
from django.utils import timezone


class BaseModel(models.Model):
    created_at = models.DateTimeField(_('Data de Criação'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Data de Atualização'), auto_now=True)

    class Meta:
        abstract = True


class Paciente(BaseModel):
    SEXO_CHOICES = (
        ('M', _('Masculino')),
        ('F', _('Feminino')),
        ('O', _('Outro')),
    )
    ORIGEM_MANUAL = 'manual'
    ORIGEM_SOULMV = 'soulmv'
    ORIGEM_CHOICES = (
        (ORIGEM_MANUAL, _('Manual')),
        (ORIGEM_SOULMV, _('Soul MV')),
    )

    nome = models.CharField(_('Nome Completo'), max_length=255)
    data_nascimento = models.DateField(_('Data de Nascimento'))
    cpf = models.CharField(
        _('CPF'), max_length=14, unique=True, null=True, blank=True, help_text='Formato: 000.000.000-00'
    )
    rg = models.CharField(_('RG'), max_length=20, blank=True, null=True)
    sexo = models.CharField(_('Sexo'), max_length=1, choices=SEXO_CHOICES, null=True, blank=True)
    telefone = models.CharField(_('Telefone'), max_length=20, blank=True, null=True)
    celular = models.CharField(_('Celular'), max_length=20, null=True, blank=True)
    email = models.EmailField(_('Email'), blank=True, null=True)
    observacoes = models.TextField(_('Observações'), blank=True, null=True)
    ativo = models.BooleanField(_('Ativo'), default=True)
    codigo_cidadao = models.CharField(_('Código cidadão (Soul MV)'), max_length=20, unique=True, null=True, blank=True)
    cns = models.CharField(_('CNS'), max_length=15, null=True, blank=True, db_index=True)
    nome_social = models.CharField(_('Nome social'), max_length=255, null=True, blank=True)
    origem = models.CharField(_('Origem'), max_length=10, choices=ORIGEM_CHOICES, default=ORIGEM_MANUAL)

    class Meta:
        verbose_name = _('Paciente')
        verbose_name_plural = _('Pacientes')
        ordering = ['nome']
        indexes = [
            models.Index(fields=['cpf']),
            models.Index(fields=['nome']),
        ]

    def __str__(self):
        return f"{self.nome} - {self.cpf or 'sem CPF'}"


class Agendamento(BaseModel):
    paciente = models.ForeignKey(
        Paciente, on_delete=models.PROTECT, related_name='agendamentos', verbose_name=_('Paciente')
    )
    solicitacao = models.CharField(_('Solicitação'), max_length=20, unique=True)
    item_agendamento = models.CharField(_('Item de agendamento'), max_length=255)
    data_agenda = models.DateTimeField(_('Data da agenda'), null=True, blank=True)

    class Meta:
        verbose_name = _('Agendamento')
        verbose_name_plural = _('Agendamentos')
        ordering = ['-data_agenda']
        indexes = [models.Index(fields=['paciente', 'data_agenda'])]

    def __str__(self):
        return f"{self.solicitacao} - {self.item_agendamento}"


class ExecucaoImportacao(models.Model):
    STATUS_EXECUTANDO = 'executando'
    STATUS_SUCESSO = 'sucesso'
    STATUS_ERRO = 'erro'
    STATUS_IGNORADO = 'ignorado'
    STATUS_CHOICES = (
        (STATUS_EXECUTANDO, _('Executando')),
        (STATUS_SUCESSO, _('Sucesso')),
        (STATUS_ERRO, _('Erro')),
        (STATUS_IGNORADO, _('Ignorado')),
    )

    iniciado_em = models.DateTimeField(_('Iniciado em'), default=timezone.now)
    finalizado_em = models.DateTimeField(_('Finalizado em'), null=True, blank=True)
    status = models.CharField(_('Status'), max_length=12, choices=STATUS_CHOICES, default=STATUS_EXECUTANDO)
    arquivo = models.CharField(_('Arquivo'), max_length=500)
    sha256 = models.CharField(_('SHA-256'), max_length=64, blank=True, db_index=True)
    linhas_lidas = models.PositiveIntegerField(_('Linhas lidas'), default=0)
    pacientes_criados = models.PositiveIntegerField(_('Pacientes criados'), default=0)
    agendamentos_criados = models.PositiveIntegerField(_('Agendamentos criados'), default=0)
    linhas_rejeitadas = models.PositiveIntegerField(_('Linhas rejeitadas'), default=0)
    detalhes_rejeicao = models.JSONField(_('Detalhes da rejeição'), default=list, blank=True)
    erro = models.TextField(_('Erro'), blank=True)

    class Meta:
        verbose_name = _('Execução de importação')
        verbose_name_plural = _('Execuções de importação')
        ordering = ['-iniciado_em']

    def __str__(self):
        return f"{self.iniciado_em:%d/%m/%Y %H:%M} - {self.status}"


def template_upload_path(instance, filename):
    """Define o caminho para upload do template PDF."""
    ext = filename.split('.')[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    return os.path.join('templates', str(instance.criado_por.id), filename)


class TemplateDocumento(BaseModel):
    nome = models.CharField(_('Nome do Template'), max_length=255)
    descricao = models.TextField(_('Descrição'), blank=True, null=True)
    arquivo_template = models.FileField(
        _('Arquivo do Template PDF'),
        upload_to=template_upload_path,
        validators=[FileExtensionValidator(allowed_extensions=['pdf'])],
        blank=True,
        null=True,
        help_text=_('Arquivo PDF do template (opcional para registros antigos).')
    )
    conteudo = models.TextField(
        _('Conteúdo do Template'),
        blank=True,
        null=True,
        help_text=_('Conteúdo textual opcional para o template (usado apenas no admin).')
    )
    criado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name=_('Criado por'))
    ativo = models.BooleanField(_('Ativo'), default=True)

    class Meta:
        verbose_name = _('Template de Documento')
        verbose_name_plural = _('Templates de Documentos')
        ordering = ['nome']

    def __str__(self):
        return self.nome


class CampoTemplateDocumento(BaseModel):
    TIPO_CAMPO_CHOICES = (
        ('text', _('Texto')),
        ('textarea', _('Texto Longo')),
        ('number', _('Número')),
        ('date', _('Data')),
        ('boolean', _('Booleano')),
        ('cpf', _('CPF')),
        ('email', _('E-mail')),
        ('telefone', _('Telefone')),
        ('checkbox', _('Caixa de Seleção')),
        ('select', _('Seleção')),
        ('assinatura', _('Assinatura')),
        ('imagem', _('Imagem')),
        ('label', _('Texto Fixo')),
    )

    template = models.ForeignKey(
        TemplateDocumento,
        on_delete=models.CASCADE,
        related_name='campos',
        verbose_name=_('Template')
    )
    nome_campo = models.CharField(_('Nome do Campo'), max_length=255)
    tipo_campo = models.CharField(
        _('Tipo do Campo'),
        max_length=20,
        choices=TIPO_CAMPO_CHOICES,
        default='text'
    )
    descricao = models.TextField(_('Descrição do Campo'), blank=True, null=True)

    pagina = models.PositiveIntegerField(
        _('Página do PDF'),
        default=1,
        help_text=_('Número da página do PDF onde este campo aparece.')
    )

    posicao = models.JSONField(
        _('Posição do Campo'),
        help_text=_('Ex: {"x": 100, "y": 200, "font_size": 12, "font_name": "Helvetica"}')
    )

    obrigatorio = models.BooleanField(_('Campo Obrigatório'), default=False)

    atributo_paciente = models.CharField(
        _('Atributo do Paciente'),
        max_length=50,
        blank=True,
        null=True,
        help_text=_("Ex: 'nome', 'cpf', etc.")
    )

    validacoes = models.JSONField(
        _('Validações'),
        blank=True,
        null=True,
        help_text=_("Ex: {'min_length': 3, 'max_length': 10, 'regex': '^\\d+$'}")
    )

    visivel_se = models.JSONField(
        _('Visível se'),
        blank=True,
        null=True,
        help_text=_("Ex: {'campo': 'tipo_documento', 'valor': 'Termo'}")
    )

    opcoes = models.JSONField(
        _('Opções (para select/checkbox)'),
        blank=True,
        null=True,
        help_text=_("Ex: ['Sim', 'Não', 'Talvez']")
    )

    ordem_formulario = models.PositiveIntegerField(
        _('Ordem no Formulário'),
        default=0,
        help_text=_("Ordem de exibição no formulário.")
    )

    class Meta:
        verbose_name = _('Campo do Template')
        verbose_name_plural = _('Campos do Template')
        ordering = ['template', 'ordem_formulario', 'nome_campo']

    def __str__(self):
        return f"{self.template.nome} - {self.nome_campo}"

    def save(self, *args, **kwargs):
        """
        Ao salvar, garante que cada opção (se for select ou checkbox) tem um 'id' único.
        """
        import uuid
        if self.tipo_campo in ['select', 'checkbox'] and isinstance(self.opcoes, list):
            novas_opcoes = []
            for idx, opc in enumerate(self.opcoes):
                if isinstance(opc, dict):
                    opc = dict(opc)
                    if 'id' not in opc:
                        opc['id'] = str(uuid.uuid4())
                    novas_opcoes.append(opc)
                else:
                    # transforma string em dict
                    novas_opcoes.append({'id': str(uuid.uuid4()), 'texto': str(opc)})
            self.opcoes = novas_opcoes
        super().save(*args, **kwargs)



def documento_upload_path(instance, filename):
    """Define o caminho para upload de documentos (opcional)."""
    ext = filename.split('.')[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    return os.path.join('documentos', str(instance.paciente.id), filename)


class Documento(BaseModel):
    paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE, related_name='documentos', verbose_name=_('Paciente'))
    template = models.ForeignKey(TemplateDocumento, on_delete=models.SET_NULL, null=True, verbose_name=_('Template'))
    nome = models.CharField(_('Nome do Documento'), max_length=255)
    arquivo = models.FileField(
        _('Arquivo'),
        upload_to=documento_upload_path,
        blank=True,
        null=True,
        help_text=_('Campo opcional para compatibilidade com admin (não usado na geração de PDFs).')
    )
    data_emissao = models.DateField(_('Data de Emissão'), auto_now_add=True)
    emitido_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name=_('Emitido por'))
    observacoes = models.TextField(_('Observações'), blank=True, null=True)

    class Meta:
        verbose_name = _('Documento')
        verbose_name_plural = _('Documentos')
        ordering = ['-data_emissao']
        indexes = [
            models.Index(fields=['paciente', 'template']),
            models.Index(fields=['data_emissao']),
        ]

    def __str__(self):
        return f"{self.nome} - {self.paciente}"

    def registrar_acao(self, usuario, acao):
        """
        Registra uma ação no modelo HistoricoAcaoDocumento.
        """
        HistoricoAcaoDocumento.objects.create(
            documento=self,
            usuario=usuario,
            acao=acao,
            data_hora=datetime.now(tz=pytz.timezone('America/Sao_Paulo'))
        )

    def delete(self, *args, **kwargs):
        """Remove o arquivo associado, se existir, ao deletar o documento."""
        if self.arquivo and os.path.isfile(self.arquivo.path):
            os.remove(self.arquivo.path)
        super().delete(*args, **kwargs)


class CampoPreenchidoDocumento(BaseModel):
    documento = models.ForeignKey(Documento, on_delete=models.CASCADE, related_name='campos_preenchidos', verbose_name=_('Documento'))
    campo_template = models.ForeignKey(CampoTemplateDocumento, on_delete=models.CASCADE, verbose_name=_('Campo do Template'))
    valor = models.TextField(_('Valor Preenchido'), blank=True)

    class Meta:
        verbose_name = _('Campo Preenchido do Documento')
        verbose_name_plural = _('Campos Preenchidos do Documento')
        ordering = ['documento', 'campo_template']

    def __str__(self):
        return f"{self.documento.nome} - {self.campo_template.nome_campo}: {self.valor}"

    def clean(self):
        """
        Valida o valor preenchido com base no tipo_campo do CampoTemplateDocumento.
        """
        from django.core.exceptions import ValidationError
        tipo = self.campo_template.tipo_campo
        if self.campo_template.obrigatorio and not self.valor:
            raise ValidationError(_('Este campo é obrigatório.'))
        if tipo == 'number':
            try:
                float(self.valor)
            except ValueError:
                raise ValidationError(_('O valor deve ser um número.'))
        elif tipo == 'date':
            try:
                datetime.strptime(self.valor, '%Y-%m-%d')
            except ValueError:
                raise ValidationError(_('O valor deve ser uma data no formato AAAA-MM-DD.'))


class HistoricoAcaoDocumento(BaseModel):
    documento = models.ForeignKey(Documento, on_delete=models.CASCADE, related_name='historico_acoes', verbose_name=_('Documento'))
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name=_('Usuário'))
    acao = models.CharField(_('Ação'), max_length=255)
    data_hora = models.DateTimeField(_('Data e Hora'), default=timezone.now)

    class Meta:
        verbose_name = _('Histórico de Ação do Documento')
        verbose_name_plural = _('Históricos de Ações do Documento')
        ordering = ['-data_hora']

    def __str__(self):
        return f"{self.documento} - {self.acao} ({self.data_hora})"