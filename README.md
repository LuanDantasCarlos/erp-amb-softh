# Sistema de Gerenciamento Ambulatorial

Sistema de gerenciamento ambulatorial desenvolvido com Django e Django Rest Framework para cadastro de pacientes e geração de documentos médicos.

## Funcionalidades

- Cadastro completo de pacientes com informações detalhadas
- Criação e gerenciamento de templates de documentos
- Geração automática de documentos em PDF
- API RESTful com autenticação por token
- Dashboard com estatísticas e informações relevantes
- Frontend responsivo e amigável

## Tecnologias

- Python 3.11
- Django 5.2
- Django REST Framework
- PostgreSQL
- Bootstrap 5
- ReportLab para geração de PDFs
- JWT para autenticação da API

## Requisitos

- Python 3.8+
- PostgreSQL
- Bibliotecas Python listadas em requirements.txt

## Instalação

1. Clone o repositório:
```
git clone https://github.com/seu-usuario/sistema-ambulatorial.git
cd sistema-ambulatorial
```

2. Crie um ambiente virtual e ative-o:
```
python -m venv venv
source venv/bin/activate  # No Windows: venv\Scripts\activate
```

3. Instale as dependências:
```
pip install -r requirements.txt
```

4. Configure as variáveis de ambiente:
Copie o arquivo `.env.example` para `.env` e ajuste as configurações conforme necessário.

5. Execute as migrações:
```
python manage.py migrate
```

6. Crie um superusuário:
```
python manage.py createsuperuser
```

7. Execute o servidor de desenvolvimento:
```
python manage.py runserver
```

8. Acesse o sistema em http://localhost:8000

## Ambiente de Produção

Para ambientes de produção, recomenda-se:

1. Definir `DEBUG=False` no arquivo `.env`
2. Configurar um servidor web adequado (Nginx, Apache)
3. Utilizar Gunicorn ou uWSGI como servidor WSGI
4. Configurar um banco de dados PostgreSQL dedicado
5. Implementar HTTPS usando certificados SSL

## Usuário Padrão (Ambiente de Desenvolvimento)

- Usuário: admin
- Senha: admin123

## Estrutura do Projeto

- `ambulatorio/`: Configurações principais do projeto Django
- `core/`: Aplicação principal com modelos, views e templates
- `static/`: Arquivos estáticos (CSS, JS, imagens)
- `templates/`: Templates HTML do sistema
- `media/`: Arquivos gerados pelo sistema (documentos, etc.)

## Licença

Este projeto está licenciado sob a [MIT License](LICENSE).