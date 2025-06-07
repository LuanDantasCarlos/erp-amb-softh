from rest_framework import serializers
import os
import shutil
import uuid
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
                instance.arquivo_template.save(file_name, File(f))
            instance.save()
        return instance


class DocumentoSerializer(serializers.ModelSerializer):
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
    class Meta:
        model = CampoPreenchidoDocumento
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class GerarDocumentoSerializer(serializers.Serializer):
    paciente_id = serializers.IntegerField()
    template_id = serializers.IntegerField()
    nome_documento = serializers.CharField(max_length=255)
    observacoes = serializers.CharField(required=False, allow_blank=True)
    campos = serializers.DictField(
        child=serializers.CharField(allow_blank=True),
        required=True,
        help_text="Dicionário com os valores para os campos do template (campo_id: valor)"
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
                if campo.obrigatorio and str(campo.id) not in value:
                    raise serializers.ValidationError(f"O campo obrigatório '{campo.nome_campo}' (ID: {campo.id}) não foi preenchido.")
                if str(campo.id) in value:
                    valor = value[str(campo.id)]
                    if campo.tipo_campo == 'number' and valor:
                        try:
                            float(valor)
                        except ValueError:
                            raise serializers.ValidationError(f"O campo '{campo.nome_campo}' (ID: {campo.id}) deve ser um número.")
                    elif campo.tipo_campo == 'date' and valor:
                        try:
                            from datetime import datetime
                            datetime.strptime(valor, '%Y-%m-%d')
                        except ValueError:
                            raise serializers.ValidationError(f"O campo '{campo.nome_campo}' (ID: {campo.id}) deve ser uma data no formato AAAA-MM-DD.")
                    elif campo.tipo_campo == 'boolean' and valor:
                        if valor not in ['True', 'False']:
                            raise serializers.ValidationError(f"O campo '{campo.nome_campo}' (ID: {campo.id}) deve ser 'True' ou 'False'.")
        except TemplateDocumento.DoesNotExist:
            pass
        return value