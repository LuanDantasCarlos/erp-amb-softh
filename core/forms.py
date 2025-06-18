from datetime import datetime
from django import forms
from django.core.exceptions import ValidationError
from .models import Paciente, TemplateDocumento, Documento, CampoTemplateDocumento
import json

class PacienteForm(forms.ModelForm):
    class Meta:
        model = Paciente
        fields = [
            'nome', 'data_nascimento', 'cpf', 'rg', 'sexo',
            'telefone', 'celular', 'email', 'observacoes', 'ativo'
        ]
        widgets = {
            'data_nascimento': forms.DateInput(attrs={'type': 'date'}),
            'observacoes': forms.Textarea(attrs={'rows': 4}),
            'sexo': forms.Select(choices=Paciente.SEXO_CHOICES),
        }

    def clean_cpf(self):
        cpf = self.cleaned_data.get('cpf', '')
        cpf_nums = ''.join(filter(str.isdigit, cpf))
        if len(cpf_nums) != 11:
            raise forms.ValidationError("CPF deve conter 11 dígitos.")
        if cpf_nums == cpf_nums[0] * 11:
            raise forms.ValidationError("CPF inválido.")
        soma = sum(int(cpf_nums[i]) * (10 - i) for i in range(9))
        resto = soma % 11
        digito1 = 0 if resto < 2 else 11 - resto
        if int(cpf_nums[9]) != digito1:
            raise forms.ValidationError("CPF inválido.")
        soma = sum(int(cpf_nums[i]) * (11 - i) for i in range(10))
        resto = soma % 11
        digito2 = 0 if resto < 2 else 11 - resto
        if int(cpf_nums[10]) != digito2:
            raise forms.ValidationError("CPF inválido.")
        return f"{cpf_nums[:3]}.{cpf_nums[3:6]}.{cpf_nums[6:9]}-{cpf_nums[9:]}"

class TemplateDocumentoForm(forms.ModelForm):
    class Meta:
        model = TemplateDocumento
        fields = ['nome', 'descricao', 'arquivo_template', 'ativo']
        widgets = {
            'descricao': forms.Textarea(attrs={'rows': 3}),
            'arquivo_template': forms.FileInput(),
        }

class GerarDocumentoForm(forms.Form):
    paciente_id = forms.IntegerField(
        label="Paciente",
        widget=forms.Select(),
        required=True
    )
    template_id = forms.IntegerField(
        label="Template",
        widget=forms.Select(),
        required=True
    )
    nome_documento = forms.CharField(
        label="Nome do Documento",
        max_length=255,
        required=True
    )
    observacoes = forms.CharField(
        label="Observações",
        widget=forms.Textarea(attrs={'rows': 3}),
        required=False
    )
    campos = forms.JSONField(
        label="Campos do Template",
        required=False,
        widget=forms.HiddenInput()
    )

    def clean_paciente_id(self):
        paciente_id = self.cleaned_data.get('paciente_id')
        try:
            Paciente.objects.get(id=paciente_id)
        except Paciente.DoesNotExist:
            raise forms.ValidationError("Paciente não encontrado.")
        return paciente_id

    def clean_template_id(self):
        template_id = self.cleaned_data.get('template_id')
        try:
            TemplateDocumento.objects.get(id=template_id)
        except TemplateDocumento.DoesNotExist:
            raise forms.ValidationError("Template não encontrado.")
        return template_id

    def clean(self):
        cleaned_data = super().clean()
        # Demais validações podem ser feitas no serializer/views
        return cleaned_data