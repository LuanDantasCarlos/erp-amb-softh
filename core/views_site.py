"""
Views para o frontend do site
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.template import Template as DjangoTemplate, Context
from django.db.models import F, Q
from django.utils import timezone
from datetime import date, timedelta
from django.http import HttpResponse, FileResponse
import os
from django.http import JsonResponse
from django.forms.models import model_to_dict
from reportlab.pdfbase import pdfmetrics




from .models import Paciente, TemplateDocumento, Documento
from .models import Paciente, TemplateDocumento, Documento, CampoTemplateDocumento, CampoPreenchidoDocumento
from .forms import GerarDocumentoForm,TemplateDocumentoForm, PacienteForm
from core.serializers import GerarDocumentoSerializer
from .utils import gerar_documento_pdf, calcular_maxchars_textarea
from .agenda import anotar_atendimento_no_dia, anotar_proximo_atendimento, filtrar_atendimento_no_dia


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
PACIENTES_POR_PAGINA = 25


def _parse_data_param(valor: str):
    try:
        return date.fromisoformat(valor) if valor else None
    except ValueError:
        return None


def _filtro_busca(search: str) -> Q:
    filtro = (
        Q(nome__icontains=search)
        | Q(nome_social__icontains=search)
        | Q(cpf__icontains=search)
        | Q(cns__icontains=search)
        | Q(codigo_cidadao__icontains=search)
        | Q(email__icontains=search)
        | Q(celular__icontains=search)
    )
    digitos = ''.join(ch for ch in search if ch.isdigit())
    if len(digitos) == 11 and digitos == search.strip():
        # CPF digitado sem máscara: o banco guarda 000.000.000-00.
        filtro |= Q(cpf=f'{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}')
    return filtro


@login_required
def paciente_list(request):
    """
    Lista de pacientes, com filtro opcional pela data do atendimento (Agendamento.data_agenda).
    """
    search = request.GET.get('search', '').strip()
    ativo = request.GET.get('ativo', '')
    data_param = request.GET.get('data', '').strip()
    data_filtro = _parse_data_param(data_param)
    if data_param and data_filtro is None:
        messages.warning(request, 'Data do atendimento inválida; filtro ignorado.')

    queryset = Paciente.objects.all()
    if search:
        queryset = queryset.filter(_filtro_busca(search))
    if ativo in ('0', '1'):
        queryset = queryset.filter(ativo=ativo == '1')

    if data_filtro:
        queryset = filtrar_atendimento_no_dia(queryset, data_filtro)
    else:
        queryset = anotar_proximo_atendimento(queryset).order_by('nome', 'pk')

    paginator = Paginator(queryset, PACIENTES_POR_PAGINA)
    pacientes = paginator.get_page(request.GET.get('page', 1))

    filtros = request.GET.copy()
    filtros.pop('page', None)
    filtros_sem_data = filtros.copy()
    filtros_sem_data.pop('data', None)
    hoje = timezone.localdate()

    context = {
        'pacientes': pacientes,
        'search': search,
        'ativo': ativo,
        'data_filtro': data_filtro,
        'hoje': hoje,
        'amanha': hoje + timedelta(days=1),
        'querystring': filtros.urlencode(),
        'querystring_sem_data': filtros_sem_data.urlencode(),
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
    agendamentos = paciente.agendamentos.order_by(F('data_agenda').desc(nulls_last=True), '-pk')

    context = {
        'paciente': paciente,
        'total_documentos': total_documentos,
        'ultimo_documento': ultimo_documento,
        'agendamentos': agendamentos,
        'hoje': timezone.localdate(),
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

def _pacientes_para_selecao():
    """Pacientes ativos para o select, anotados com o atendimento de hoje (uma única query)."""
    return anotar_atendimento_no_dia(Paciente.objects.filter(ativo=True), timezone.localdate()).order_by('nome')


@login_required
def gerar_documento(request):
    initial = {}
    if request.GET.get('paciente_id'):
        initial['paciente_id'] = request.GET.get('paciente_id')
    if request.GET.get('template_id'):
        initial['template_id'] = request.GET.get('template_id')

    from_url = request.META.get('HTTP_REFERER')
    selected_paciente = None
    selected_template = None
    campos_template = None

    if request.method == 'POST':
        form = GerarDocumentoForm(request.POST)

        if 'preview' in request.POST:
            if form.is_valid():
                try:
                    selected_paciente = Paciente.objects.get(id=form.cleaned_data['paciente_id'])
                    selected_template = TemplateDocumento.objects.get(id=form.cleaned_data['template_id'])
                    campos_template = CampoTemplateDocumento.objects.filter(template=selected_template)
                    messages.info(request, 'Visualização carregada com sucesso.')
                except Exception as e:
                    messages.error(request, f'Erro ao carregar visualização: {str(e)}')
            else:
                messages.error(request, f'Erro no formulário: {form.errors}')
        elif form.is_valid():
            paciente_id = form.cleaned_data['paciente_id']
            template_id = form.cleaned_data['template_id']
            nome_documento = form.cleaned_data['nome_documento']
            observacoes = form.cleaned_data.get('observacoes', '')

            campos_valores = {}
            for campo in CampoTemplateDocumento.objects.filter(template_id=template_id):
                chave = str(campo.id)
                if campo.tipo_campo == 'checkbox':
                    valor = request.POST.getlist(f'campo_{chave}[]')
                else:
                    valor = request.POST.get(f'campo_{chave}', '')
                campos_valores[chave] = valor

            serializer = GerarDocumentoSerializer(data={
                'paciente_id': paciente_id,
                'template_id': template_id,
                'nome_documento': nome_documento,
                'observacoes': observacoes,
                'campos': campos_valores,
            })

            if serializer.is_valid():
                try:
                    paciente = Paciente.objects.get(id=paciente_id)
                    template = TemplateDocumento.objects.get(id=template_id)

                    documento = Documento.objects.create(
                        paciente=paciente,
                        template=template,
                        nome=nome_documento,
                        emitido_por=request.user,
                        observacoes=observacoes
                    )
                    documento.registrar_acao(request.user, "gerado")
                    messages.info(request, 'Documento criado com sucesso.')

                    for campo in CampoTemplateDocumento.objects.filter(template=template):
                        valor = campos_valores.get(str(campo.id), '')
                        CampoPreenchidoDocumento.objects.create(
                            documento=documento,
                            campo_template=campo,
                            valor=valor
                        )
                    messages.info(request, 'Campos preenchidos salvos.')

                    if not template.arquivo_template:
                        messages.error(request, 'O template selecionado não possui um arquivo PDF associado.')
                        return render(request, 'core/gerar_documento.html', {
                            'form': form,
                            'pacientes': _pacientes_para_selecao(),
                            'templates': TemplateDocumento.objects.filter(ativo=True),
                            'from_url': from_url,
                        })

                    messages.info(request, 'Gerando PDF...')
                    pdf_buffer = gerar_documento_pdf(paciente, template, campos_valores)
                    if pdf_buffer:
                        messages.success(request, 'PDF gerado com sucesso.')
                        return FileResponse(
                            pdf_buffer,
                            as_attachment=True,
                            filename=f"{nome_documento}.pdf",
                            content_type='application/pdf'
                        )
                    else:
                        documento.delete()
                        messages.error(request, 'Erro ao gerar o PDF.')
                except Exception as e:
                    messages.error(request, f'Erro ao gerar o documento: {str(e)}')
            else:
                messages.error(request, f'Erro na validação dos campos: {serializer.errors}')
        else:
            messages.error(request, f'Erro no formulário: {form.errors}')
    else:
        form = GerarDocumentoForm(initial=initial)

    pacientes = _pacientes_para_selecao()
    templates = TemplateDocumento.objects.filter(ativo=True).order_by('nome')

    context = {
        'form': form,
        'pacientes': pacientes,
        'templates': templates,
        'from_url': from_url,
        'selected_paciente': selected_paciente,
        'selected_template': selected_template,
        'campos_template': campos_template,
    }

    return render(request, 'core/gerar_documento.html', context)

def calcular_maxlength_textarea(width_pt, height_pt, font_name="Helvetica", font_size=12, line_height_factor=1.2):
    line_height = font_size * line_height_factor
    max_lines = int(height_pt // line_height)
    char_width = pdfmetrics.stringWidth('a', font_name, font_size)
    chars_per_line = int(width_pt // char_width) if char_width else 0
    maxlength = max_lines * chars_per_line
    return maxlength

@login_required
def campos_template_json(request, template_id):
    campos = CampoTemplateDocumento.objects.filter(template_id=template_id)
    campos_list = []

    for campo in campos:
        campo_dict = {
            'id': campo.id,
            'nome': campo.nome_campo,
            'tipo': campo.tipo_campo,
            'descricao': campo.descricao,
            'pagina': campo.pagina,
            'posicao': campo.posicao,
            'obrigatorio': campo.obrigatorio,
            'atributo_paciente': campo.atributo_paciente,
        }

        # Calcule maxlength apenas se for textarea e se width/height existirem
        if campo.tipo_campo == 'textarea':
            pos = campo.posicao if isinstance(campo.posicao, dict) else campo.posicao[0]
            width = pos.get('width')
            height = pos.get('height')
            font_size = pos.get('font_size', 12)
            font_name = pos.get('font_name', "Helvetica")
            if width and height:
                # Use a função realista do utils.py!
                campo_dict['maxlength'] = calcular_maxchars_textarea(width, height, font_name, font_size)

        if campo.tipo_campo in ['checkbox', 'select'] and campo.opcoes:
            opcoes = []
            for idx, opc in enumerate(campo.opcoes):
                if isinstance(opc, dict):
                    opc_copy = dict(opc)
                    if 'id' not in opc_copy:
                        opc_copy['id'] = str(idx + 1)
                    opcoes.append(opc_copy)
                else:
                    opcoes.append({'id': str(idx+1), 'texto': str(opc)})
            campo_dict['opcoes'] = opcoes

        campos_list.append(campo_dict)

    return JsonResponse(campos_list, safe=False)

@login_required
def paciente_json(request, paciente_id):
    try:
        paciente = Paciente.objects.get(id=paciente_id)
        paciente_dict = model_to_dict(paciente)
        return JsonResponse(paciente_dict)
    except Paciente.DoesNotExist:
        return JsonResponse({'erro': 'Paciente não encontrado'}, status=404)