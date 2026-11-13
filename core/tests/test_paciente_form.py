import pytest

from core.forms import PacienteForm

pytestmark = pytest.mark.django_db


def test_form_aceita_paciente_sem_cpf_sexo_celular():
    form = PacienteForm(data={'nome': 'PACIENTE TESTE', 'data_nascimento': '1950-02-01', 'ativo': True})

    assert form.is_valid(), form.errors
    paciente = form.save()
    assert paciente.cpf is None
    assert paciente.sexo is None
    assert paciente.celular is None


def test_form_continua_validando_cpf_informado():
    form = PacienteForm(data={'nome': 'X', 'data_nascimento': '1950-02-01', 'cpf': '123.456.789-00'})

    assert not form.is_valid()
    assert 'cpf' in form.errors


def test_form_edicao_preserva_campos_do_soulmv():
    form = PacienteForm(data={'nome': 'A', 'data_nascimento': '1950-02-01', 'ativo': True})
    paciente = form.save()
    paciente.codigo_cidadao = '1000001'
    paciente.origem = 'soulmv'
    paciente.save()

    edicao = PacienteForm(data={'nome': 'B', 'data_nascimento': '1950-02-01', 'ativo': True}, instance=paciente)
    assert edicao.is_valid(), edicao.errors
    edicao.save()
    paciente.refresh_from_db()
    assert (paciente.codigo_cidadao, paciente.origem) == ('1000001', 'soulmv')
