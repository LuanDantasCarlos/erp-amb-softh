"""
Serializers for the core app
"""
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Paciente, TemplateDocumento, Documento


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model"""
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email']
        read_only_fields = ['id']


class PacienteSerializer(serializers.ModelSerializer):
    """Serializer for Paciente model"""
    class Meta:
        model = Paciente
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate_cpf(self, value):
        """
        Validate CPF format
        """
        # Remove all non-digit characters
        cpf = ''.join(filter(str.isdigit, value))
        
        # Check if CPF has 11 digits
        if len(cpf) != 11:
            raise serializers.ValidationError("CPF deve conter 11 dígitos.")
        
        # Check if CPF is valid
        if cpf == cpf[0] * 11:
            raise serializers.ValidationError("CPF inválido.")
        
        # Verify CPF validation algorithm
        soma = 0
        for i in range(9):
            soma += int(cpf[i]) * (10 - i)
        resto = soma % 11
        if resto < 2:
            digito1 = 0
        else:
            digito1 = 11 - resto
        
        if int(cpf[9]) != digito1:
            raise serializers.ValidationError("CPF inválido.")
        
        soma = 0
        for i in range(10):
            soma += int(cpf[i]) * (11 - i)
        resto = soma % 11
        if resto < 2:
            digito2 = 0
        else:
            digito2 = 11 - resto
        
        if int(cpf[10]) != digito2:
            raise serializers.ValidationError("CPF inválido.")
        
        # Format CPF
        return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"


class TemplateDocumentoSerializer(serializers.ModelSerializer):
    """Serializer for TemplateDocumento model"""
    criado_por_info = UserSerializer(source='criado_por', read_only=True)
    
    class Meta:
        model = TemplateDocumento
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate_conteudo(self, value):
        """
        Validate that the content has valid markers
        """
        # Basic validation - check if there are any template markers
        if '{{' not in value or '}}' not in value:
            raise serializers.ValidationError(
                "O conteúdo deve conter pelo menos um marcador (exemplo: {{ paciente.nome }})."
            )
        return value


class DocumentoSerializer(serializers.ModelSerializer):
    """Serializer for Documento model"""
    paciente_info = PacienteSerializer(source='paciente', read_only=True)
    template_info = TemplateDocumentoSerializer(source='template', read_only=True)
    emitido_por_info = UserSerializer(source='emitido_por', read_only=True)
    
    class Meta:
        model = Documento
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'arquivo']


class GerarDocumentoSerializer(serializers.Serializer):
    """Serializer for document generation endpoint"""
    paciente_id = serializers.IntegerField()
    template_id = serializers.IntegerField()
    nome_documento = serializers.CharField(max_length=255)
    observacoes = serializers.CharField(required=False, allow_blank=True)
    
    def validate_paciente_id(self, value):
        """Validate that the patient exists"""
        try:
            Paciente.objects.get(id=value)
        except Paciente.DoesNotExist:
            raise serializers.ValidationError("Paciente não encontrado.")
        return value
    
    def validate_template_id(self, value):
        """Validate that the template exists"""
        try:
            TemplateDocumento.objects.get(id=value)
        except TemplateDocumento.DoesNotExist:
            raise serializers.ValidationError("Template não encontrado.")
        return value
