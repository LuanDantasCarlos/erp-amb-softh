"""
Views para o frontend do site
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.template import Template as DjangoTemplate, Context
from django.db.models import Q
from django.http import HttpResponse, FileResponse
import os

from .models import Paciente, TemplateDocumento, Documento
from .forms import PacienteForm, TemplateDocumentoForm, GerarDocumentoForm
from .utils import gerar_documento_pdf


@login_required
def home(request):
    """
    Página inicial do sistema
    """
    # Contadores
    total_pacientes = Paciente.objects.count()
    total_templates = TemplateDocumento.objects.count()
    total_documentos = Documento.objects.count()
    
    # Itens recentes
    pacientes_recentes = Paciente.objects.filter(ativo=True).order_by('-created_at')[:5]
    documentos_recentes = Documento.objects.order_by('-data_emissao')[:5]
    
    context = {
        'total_pacientes': total_pacientes,
        'total_templates': total_templates,
        'total_documentos': total_documentos,
        'pacientes_recentes': pacientes_recentes,
        'documentos_recentes': documentos_recentes,
    }
    
    return render(request, 'core/home.html', context)


# Views de Pacientes
@login_required
def paciente_list(request):
    """
    Lista de pacientes
    """
    # Filtros
    search = request.GET.get('search', '')
    # cidade = request.GET.get('cidade', '')
    # estado = request.GET.get('estado', '')
    ativo = request.GET.get('ativo', '')
    
    # Consulta base
    queryset = Paciente.objects.all()
    
    # Aplicar filtros
    if search:
        queryset = queryset.filter(
            Q(nome__icontains=search) | 
            Q(cpf__icontains=search) | 
            Q(email__icontains=search) |
            Q(celular__icontains=search)
        )
    
    # if cidade:
    #     queryset = queryset.filter(cidade=cidade)
    
    # if estado:
    #     queryset = queryset.filter(estado=estado)
    
    if ativo:
        queryset = queryset.filter(ativo=ativo == '1')
    
    # Ordenação
    queryset = queryset.order_by('nome')
    
    # Paginação
    paginator = Paginator(queryset, 10)
    page_number = request.GET.get('page', 1)
    pacientes = paginator.get_page(page_number)
    
    # Dados para filtros
    # cidades = Paciente.objects.values_list('cidade', flat=True).distinct().order_by('cidade')
    # estados = Paciente.objects.values_list('estado', flat=True).distinct().order_by('estado')
    
    context = {
        'pacientes': pacientes,
    }
    
    return render(request, 'core/paciente_list.html', context)


@login_required
def paciente_create(request):
    """
    Criação de novo paciente
    """
    if request.method == 'POST':
        form = PacienteForm(request.POST)
        if form.is_valid():
            paciente = form.save()
            messages.success(request, 'Paciente cadastrado com sucesso!')
            return redirect('paciente_detail', pk=paciente.id)
    else:
        form = PacienteForm()
    
    return render(request, 'core/paciente_form.html', {'form': form})


@login_required
def paciente_update(request, pk):
    """
    Atualização de paciente
    """
    paciente = get_object_or_404(Paciente, pk=pk)
    
    if request.method == 'POST':
        form = PacienteForm(request.POST, instance=paciente)
        if form.is_valid():
            form.save()
            messages.success(request, 'Paciente atualizado com sucesso!')
            return redirect('paciente_detail', pk=paciente.id)
    else:
        form = PacienteForm(instance=paciente)
    
    return render(request, 'core/paciente_form.html', {'form': form})


@login_required
def paciente_detail(request, pk):
    """
    Detalhes do paciente
    """
    paciente = get_object_or_404(Paciente, pk=pk)
    
    # Estatísticas
    total_documentos = Documento.objects.filter(paciente=paciente).count()
    ultimo_documento = Documento.objects.filter(paciente=paciente).order_by('-data_emissao').first()
    
    context = {
        'paciente': paciente,
        'total_documentos': total_documentos,
        'ultimo_documento': ultimo_documento,
    }
    
    return render(request, 'core/paciente_detail.html', context)


@login_required
def paciente_documentos(request, pk):
    """
    Documentos do paciente
    """
    paciente = get_object_or_404(Paciente, pk=pk)
    documentos = Documento.objects.filter(paciente=paciente).order_by('-data_emissao')
    
    context = {
        'paciente': paciente,
        'documentos': documentos,
    }
    
    return render(request, 'core/paciente_documentos.html', context)


# Views de Templates
@login_required
def template_list(request):
    """
    Lista de templates
    """
    # Filtros
    search = request.GET.get('search', '')
    ativo = request.GET.get('ativo', '')
    
    # Consulta base
    queryset = TemplateDocumento.objects.all()
    
    # Aplicar filtros
    if search:
        queryset = queryset.filter(
            Q(nome__icontains=search) | 
            Q(descricao__icontains=search)
        )
    
    if ativo:
        queryset = queryset.filter(ativo=ativo == '1')
    
    # Ordenação
    queryset = queryset.order_by('nome')
    
    # Paginação
    paginator = Paginator(queryset, 10)
    page_number = request.GET.get('page', 1)
    templates = paginator.get_page(page_number)
    
    context = {
        'templates': templates,
    }
    
    return render(request, 'core/template_list.html', context)


@login_required
def template_create(request):
    """
    Criação de novo template
    """
    if request.method == 'POST':
        form = TemplateDocumentoForm(request.POST)
        if form.is_valid():
            template = form.save(commit=False)
            template.criado_por = request.user
            template.save()
            messages.success(request, 'Template criado com sucesso!')
            return redirect('template_detail', pk=template.id)
    else:
        form = TemplateDocumentoForm()
    
    return render(request, 'core/template_form.html', {'form': form})


@login_required
def template_update(request, pk):
    """
    Atualização de template
    """
    template = get_object_or_404(TemplateDocumento, pk=pk)
    
    if request.method == 'POST':
        form = TemplateDocumentoForm(request.POST, instance=template)
        if form.is_valid():
            form.save()
            messages.success(request, 'Template atualizado com sucesso!')
            return redirect('template_detail', pk=template.id)
    else:
        form = TemplateDocumentoForm(instance=template)
    
    return render(request, 'core/template_form.html', {'form': form})


@login_required
def template_detail(request, pk):
    """
    Detalhes do template
    """
    template = get_object_or_404(TemplateDocumento, pk=pk)
    
    # Estatísticas
    total_documentos = Documento.objects.filter(template=template).count()
    ultimo_documento = Documento.objects.filter(template=template).order_by('-data_emissao').first()
    
    # Permissões
    can_edit = request.user.is_staff or template.criado_por == request.user
    
    context = {
        'template': template,
        'total_documentos': total_documentos,
        'ultimo_documento': ultimo_documento,
        'can_edit': can_edit,
    }
    
    return render(request, 'core/template_detail.html', context)


# Views de Documentos
@login_required
def documento_list(request):
    """
    Lista de documentos
    """
    # Filtros
    search = request.GET.get('search', '')
    paciente_id = request.GET.get('paciente', '')
    template_id = request.GET.get('template', '')
    
    # Consulta base
    queryset = Documento.objects.all()
    
    # Aplicar filtros
    if search:
        queryset = queryset.filter(
            Q(nome__icontains=search) | 
            Q(observacoes__icontains=search) |
            Q(paciente__nome__icontains=search)
        )
    
    if paciente_id:
        queryset = queryset.filter(paciente_id=paciente_id)
    
    if template_id:
        queryset = queryset.filter(template_id=template_id)
    
    # Ordenação
    queryset = queryset.order_by('-data_emissao')
    
    # Paginação
    paginator = Paginator(queryset, 10)
    page_number = request.GET.get('page', 1)
    documentos = paginator.get_page(page_number)
    
    # Dados para filtros
    pacientes = Paciente.objects.filter(ativo=True).order_by('nome')
    templates = TemplateDocumento.objects.filter(ativo=True).order_by('nome')
    
    context = {
        'documentos': documentos,
        'pacientes': pacientes,
        'templates': templates,
    }
    
    return render(request, 'core/documento_list.html', context)


@login_required
def documento_detail(request, pk):
    """
    Detalhes do documento
    """
    documento = get_object_or_404(Documento, pk=pk)
    
    # Verificar se o arquivo existe
    is_pdf_viewable = documento.arquivo and os.path.exists(documento.arquivo.path)
    
    context = {
        'documento': documento,
        'is_pdf_viewable': is_pdf_viewable,
    }
    
    return render(request, 'core/documento_detail.html', context)


@login_required
def documento_download(request, pk):
    """
    Download do documento
    """
    documento = get_object_or_404(Documento, pk=pk)
    
    if not documento.arquivo:
        messages.error(request, 'Arquivo não encontrado.')
        return redirect('documento_detail', pk=documento.id)
    
    # Fornecer o documento como FileResponse
    try:
        return FileResponse(
            open(documento.arquivo.path, 'rb'),
            as_attachment=True,
            filename=f"{documento.nome.replace(' ', '_')}.pdf"
        )
    except Exception as e:
        messages.error(request, f'Erro ao baixar o arquivo: {str(e)}')
        return redirect('documento_detail', pk=documento.id)


@login_required
def gerar_documento(request):
    """
    Gerar novo documento
    """
    # Preencher formulário com valores iniciais
    initial = {}
    if request.GET.get('paciente_id'):
        initial['paciente_id'] = request.GET.get('paciente_id')
    if request.GET.get('template_id'):
        initial['template_id'] = request.GET.get('template_id')
    
    # Armazenar URL de origem
    from_url = request.META.get('HTTP_REFERER', None)
    
    # Variáveis para visualização prévia
    selected_paciente = None
    selected_template = None
    preview_content = None
    
    if request.method == 'POST':
        form = GerarDocumentoForm(request.POST)
        
        # Botão de visualizar
        if 'preview' in request.POST:
            if form.is_valid():
                paciente_id = form.cleaned_data['paciente_id']
                template_id = form.cleaned_data['template_id']
                
                try:
                    selected_paciente = Paciente.objects.get(id=paciente_id)
                    selected_template = TemplateDocumento.objects.get(id=template_id)
                    
                    # Renderizar template com dados do paciente
                    django_template = DjangoTemplate(selected_template.conteudo)
                    context = Context({'paciente': selected_paciente})
                    preview_content = django_template.render(context)
                except Exception as e:
                    messages.error(request, f'Erro ao gerar visualização: {str(e)}')
                    
        # Botão de gerar documento
        elif form.is_valid():
            paciente_id = form.cleaned_data['paciente_id']
            template_id = form.cleaned_data['template_id']
            nome_documento = form.cleaned_data['nome_documento']
            observacoes = form.cleaned_data.get('observacoes', '')
            
            # Gerar documento
            success, result = gerar_documento_pdf(paciente_id, template_id, nome_documento)
            
            if success:
                # Criar registro do documento no banco de dados
                documento = Documento.objects.create(
                    paciente_id=paciente_id,
                    template_id=template_id,
                    nome=nome_documento,
                    arquivo=result,
                    emitido_por=request.user,
                    observacoes=observacoes
                )
                
                messages.success(request, 'Documento gerado com sucesso!')
                return redirect('documento_detail', pk=documento.id)
            else:
                messages.error(request, f'Erro ao gerar documento: {result}')
    else:
        form = GerarDocumentoForm(initial=initial)
    
    # Obter pacientes e templates para o formulário
    pacientes = Paciente.objects.filter(ativo=True).order_by('nome')
    templates = TemplateDocumento.objects.filter(ativo=True).order_by('nome')
    
    context = {
        'form': form,
        'pacientes': pacientes,
        'templates': templates,
        'from_url': from_url,
        'selected_paciente': selected_paciente,
        'selected_template': selected_template,
        'preview_content': preview_content,
    }
    
    return render(request, 'core/gerar_documento.html', context)