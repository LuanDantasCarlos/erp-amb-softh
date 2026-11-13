"""
Tests for the core app
"""
from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from core.models import Paciente, TemplateDocumento, Documento


class PacienteModelTest(TestCase):
    """Test the Paciente model"""
    
    def setUp(self):
        """Set up test data"""
        self.paciente = Paciente.objects.create(
            nome="João da Silva",
            data_nascimento="1980-01-01",
            cpf="123.456.789-00",
            sexo="M",
            celular="(11) 98765-4321",
            cidade="São Paulo",
            estado="SP"
        )
    
    def test_paciente_str(self):
        """Test the string representation of the Paciente model"""
        self.assertEqual(str(self.paciente), "João da Silva - 123.456.789-00")


class TemplateDocumentoModelTest(TestCase):
    """Test the TemplateDocumento model"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpassword"
        )
        self.template = TemplateDocumento.objects.create(
            nome="Atestado Médico",
            descricao="Template para atestado médico",
            conteudo="<p>Atesto que {{ paciente.nome }} esteve sob meus cuidados médicos.</p>",
            criado_por=self.user
        )
    
    def test_template_str(self):
        """Test the string representation of the TemplateDocumento model"""
        self.assertEqual(str(self.template), "Atestado Médico")


class APITests(TestCase):
    """Test the API endpoints"""
    
    def setUp(self):
        """Set up test data"""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpassword"
        )
        self.client.force_authenticate(user=self.user)
        
        # Create a patient
        self.paciente = Paciente.objects.create(
            nome="João da Silva",
            data_nascimento="1980-01-01",
            cpf="123.456.789-00",
            sexo="M",
            celular="(11) 98765-4321",
            cidade="São Paulo",
            estado="SP"
        )
        
        # Create a template
        self.template = TemplateDocumento.objects.create(
            nome="Atestado Médico",
            descricao="Template para atestado médico",
            conteudo="<p>Atesto que {{ paciente.nome }} esteve sob meus cuidados médicos.</p>",
            criado_por=self.user
        )
    
    def test_paciente_list(self):
        """Test listing patients"""
        url = reverse('paciente-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
    
    def test_paciente_create(self):
        """Test creating a patient"""
        url = reverse('paciente-list')
        data = {
            'nome': 'Maria da Silva',
            'data_nascimento': '1985-05-10',
            'cpf': '987.654.321-00',
            'sexo': 'F',
            'celular': '(11) 91234-5678',
            'cidade': 'São Paulo',
            'estado': 'SP'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Paciente.objects.count(), 2)
    
    def test_template_list(self):
        """Test listing templates"""
        url = reverse('templatedocumento-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
