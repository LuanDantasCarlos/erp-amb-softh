from rest_framework import serializers
import os
import shutil
import uuid
from datetime import datetime
import re
from django.core.files import File
from .models import Paciente, TemplateDocumento, Documento, CampoPreenchidoDocumento, CampoTemplateDocumento

class PacienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Paciente
        fields = '__all__'

class TemplateDocumentoSerializer(serializers.ModelSerializer):
    arquivo_template = serializers.CharField(required=False, allow_null=True)

    class Meta:
        model = TemplateDocumento
        fields = '__all__'
        read_only_fields = ['criado_por', 'created_at', 'updated_at']

    def create(self, validated_data):
        arquivo_path = validated_data.pop('arquivo_template', None)
        validated_data['criado_por'] = self.context['request'].user
        instance = super().create(validated_data)
        if arquivo_path and os.path.exists(arquivo_path):
            file_name = f"{uuid.uuid4()}.pdf"
            dest_path = os.path.join('templates', str(instance.criado_por.id), file_name)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            shutil.copy(arquivo_path, dest_path)
            with open(dest_path, 'rb') as f:
                instance.arquivo_template.save(file_name, File(f), save=True)
        return instance

    def update(self, instance, validated_data):
        arquivo_path = validated_data.pop('arquivo_template', None)
        instance = super().update(instance, validated_data)
        if arquivo_path and os.path.exists(arquivo_path):
            file_name = f"{uuid.uuid4()}.pdf"
            dest_path = os.path.join('templates', str(instance.criado_por.id), file_name)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            shutil.copy(arquivo_path, dest_path)
            with open(dest_path, 'rb') as f:
                instance.arquivo_template.save(file_name, File(f), save=True)
        return instance

class DocumentoSerializer(serializers.ModelSerializer):
    paciente_nome = serializers.CharField(source='paciente.nome', read_only=True)

    class Meta:
        model = Documento
        fields = '__all__'
        read_only_fields = ['emitido_por', 'data_emissao', 'created_at', 'updated_at']

    def create(self, validated_data):
        validated_data['emitido_por'] = self.context['request'].user
        return super().create(validated_data)

class CampoTemplateDocumentoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CampoTemplateDocumento
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']

class CampoPreenchidoDocumentoSerializer(serializers.ModelSerializer):
    campo_nome = serializers.CharField(source='campo.nome_campo', read_only=True)

    class Meta:
        model = CampoPreenchidoDocumento
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']

# Custom field to accept both str and list of str
class StringOrListField(serializers.Field):
    def to_internal_value(self, data):
        if isinstance(data, list):
            if not all(isinstance(i, str) for i in data):
                raise serializers.ValidationError("Todos os itens devem ser strings.")
            return data
        elif isinstance(data, str):
            return data
        else:
            raise serializers.ValidationError("Deve ser string ou lista de strings.")

    def to_representation(self, value):
        return value

class GerarDocumentoSerializer(serializers.Serializer):
    paciente_id = serializers.IntegerField()
    template_id = serializers.IntegerField()
    nome_documento = serializers.CharField(max_length=255)
    observacoes = serializers.CharField(required=False, allow_blank=True)
    campos = serializers.DictField(
        child=StringOrListField(),
        required=True,
        help_text="Dicionário com os valores para os campos do template (campo_id: valor ou lista de valores)"
    )

    def validate_paciente_id(self, value):
        if not Paciente.objects.filter(id=value).exists():
            raise serializers.ValidationError("Paciente não encontrado.")
        return value

    def validate_template_id(self, value):
        if not TemplateDocumento.objects.filter(id=value).exists():
            raise serializers.ValidationError("Template não encontrado.")
        return value

    def validate_campos(self, value):
        template_id = self.initial_data.get('template_id')
        if not template_id:
            return value

        try:
            template = TemplateDocumento.objects.get(id=template_id)
            for campo in template.campos.all():
                campo_id_str = str(campo.id)
                campo_nome = campo.nome_campo
                tipo = campo.tipo_campo
                obrigatorio = campo.obrigatorio
                opcoes = campo.opcoes or []
                validacoes = campo.validacoes or {}

                # Verifica obrigatoriedade
                if obrigatorio and campo_id_str not in value:
                    raise serializers.ValidationError(
                        f"O campo obrigatório '{campo_nome}' (ID: {campo.id}) não foi preenchido."
                    )

                if campo_id_str in value:
                    valor = value[campo_id_str]

                    # Validação por tipo
                    if tipo == 'number':
                        if isinstance(valor, list):
                            for v in valor:
                                try:
                                    float(v)
                                except ValueError:
                                    raise serializers.ValidationError(
                                        f"O campo '{campo_nome}' deve ser um número válido."
                                    )
                        else:
                            try:
                                float(valor)
                            except ValueError:
                                raise serializers.ValidationError(
                                    f"O campo '{campo_nome}' deve ser um número válido."
                                )

                    elif tipo == 'date':
                        if isinstance(valor, list):
                            for v in valor:
                                try:
                                    datetime.strptime(v, '%d/%m/%Y')
                                except ValueError:
                                    raise serializers.ValidationError(
                                        f"O campo '{campo_nome}' deve ser uma data no formato DD/MM/AAAA."
                                    )
                        else:
                            try:
                                datetime.strptime(valor, '%d/%m/%Y')
                            except ValueError:
                                raise serializers.ValidationError(
                                    f"O campo '{campo_nome}' deve ser uma data no formato DD/MM/AAAA."
                                )

                    elif tipo == 'boolean':
                        if isinstance(valor, list):
                            for v in valor:
                                if v not in ['True', 'False', True, False]:
                                    raise serializers.ValidationError(
                                        f"O campo '{campo_nome}' deve ser 'True' ou 'False'."
                                    )
                        else:
                            if valor not in ['True', 'False', True, False]:
                                raise serializers.ValidationError(
                                    f"O campo '{campo_nome}' deve ser 'True' ou 'False'."
                                )

                    elif tipo == 'cpf':
                        if isinstance(valor, list):
                            for v in valor:
                                if not re.match(r'^\d{11}$', v):
                                    raise serializers.ValidationError(
                                        f"O campo '{campo_nome}' deve conter um CPF válido (somente números, 11 dígitos)."
                                    )
                        else:
                            if not re.match(r'^\d{11}$', valor):
                                raise serializers.ValidationError(
                                    f"O campo '{campo_nome}' deve conter um CPF válido (somente números, 11 dígitos)."
                                )

                    elif tipo == 'email':
                        if isinstance(valor, list):
                            for v in valor:
                                if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', v):
                                    raise serializers.ValidationError(
                                        f"O campo '{campo_nome}' deve conter um e-mail válido."
                                    )
                        else:
                            if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', valor):
                                raise serializers.ValidationError(
                                    f"O campo '{campo_nome}' deve conter um e-mail válido."
                                )

                    elif tipo == 'telefone':
                        if isinstance(valor, list):
                            for v in valor:
                                if not re.match(r'^\d{10,11}$', v):
                                    raise serializers.ValidationError(
                                        f"O campo '{campo_nome}' deve conter um telefone válido (com DDD, apenas números)."
                                    )
                        else:
                            if not re.match(r'^\d{10,11}$', valor):
                                raise serializers.ValidationError(
                                    f"O campo '{campo_nome}' deve conter um telefone válido (com DDD, apenas números)."
                                )

                    elif tipo in ['select', 'checkbox']:
                        if isinstance(opcoes, list) and opcoes and isinstance(opcoes[0], dict) and 'id' in opcoes[0]:
                            opcoes_ids = [str(opt['id']) for opt in opcoes]
                            opcoes_labels = [str(opt.get('texto', opt['id'])) for opt in opcoes]
                        else:
                            opcoes_ids = [str(opt) for opt in opcoes]
                            opcoes_labels = opcoes_ids
                        if isinstance(valor, list):
                            for v in valor:
                                if str(v) not in opcoes_ids:
                                    raise serializers.ValidationError(
                                        f"O valor do campo '{campo_nome}' deve ser uma das opções válidas: {', '.join(opcoes_labels)}."
                                    )
                        else:
                            if str(valor) not in opcoes_ids:
                                raise serializers.ValidationError(
                                    f"O valor do campo '{campo_nome}' deve ser uma das opções válidas: {', '.join(opcoes_labels)}."
                                )

                    # Validações extras (JSONField 'validacoes')
                    if 'min_length' in validacoes:
                        if isinstance(valor, list):
                            for v in valor:
                                if len(v) < validacoes['min_length']:
                                    raise serializers.ValidationError(
                                        f"O campo '{campo_nome}' deve ter no mínimo {validacoes['min_length']} caracteres."
                                    )
                        else:
                            if len(valor) < validacoes['min_length']:
                                raise serializers.ValidationError(
                                    f"O campo '{campo_nome}' deve ter no mínimo {validacoes['min_length']} caracteres."
                                )

                    if 'max_length' in validacoes:
                        if isinstance(valor, list):
                            for v in valor:
                                if len(v) > validacoes['max_length']:
                                    raise serializers.ValidationError(
                                        f"O campo '{campo_nome}' deve ter no máximo {validacoes['max_length']} caracteres."
                                    )
                        else:
                            if len(valor) > validacoes['max_length']:
                                raise serializers.ValidationError(
                                    f"O campo '{campo_nome}' deve ter no máximo {validacoes['max_length']} caracteres."
                                )

                    if 'regex' in validacoes:
                        try:
                            regex = validacoes['regex']
                            if isinstance(valor, list):
                                for v in valor:
                                    if not re.match(regex, v):
                                        raise serializers.ValidationError(
                                            f"O valor do campo '{campo_nome}' não está no formato esperado."
                                        )
                            else:
                                if not re.match(regex, valor):
                                    raise serializers.ValidationError(
                                        f"O valor do campo '{campo_nome}' não está no formato esperado."
                                    )
                        except re.error:
                            raise serializers.ValidationError(
                                f"Regex inválido definido no campo '{campo_nome}'."
                            )

        except TemplateDocumento.DoesNotExist:
            pass

        return value