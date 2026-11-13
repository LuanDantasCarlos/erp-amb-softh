# Sistema de Gerenciamento Ambulatorial

Sistema ambulatorial em Django + Django REST Framework para cadastro de pacientes e emissão de
documentos médicos em PDF a partir de templates. Os pacientes e agendamentos novos são importados de
hora em hora do export da Central de Marcação do Soul MV.

## Funcionalidades

- Cadastro de pacientes: manual ou importado do Soul MV, nunca sobrescrito pela importação
- Templates de documento em PDF com campos posicionados e preenchimento automático com dados do paciente
- Geração e histórico de documentos
- Importação insert-only de pacientes e agendamentos do Soul MV, por command, job horário ou API
- API REST com autenticação JWT e documentação Swagger/Redoc

## Tecnologias

- Python ≥ 3.10, Django 5.2, Django REST Framework, SimpleJWT
- SQLite com WAL (o MySQL 5.7 do servidor é incompatível com Django 5.2)
- ReportLab + PyPDF2 para geração de PDFs
- WhiteNoise para arquivos estáticos; Phusion Passenger (cPanel) em produção

## Instalação local

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

cp .env.example .env               # ajuste: DEBUG=True para desenvolvimento
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Acesse em http://localhost:8000. Com `DEBUG=True` e `django-debug-toolbar` instalado, a toolbar
é ativada automaticamente.

### Testes

```bash
pytest -q
```

Os testes usam `ambulatorio.settings_test` (configurado no `pyproject.toml`) e CSVs **sintéticos** em
`core/tests/fixtures/`. Nunca coloque dados reais de pacientes em fixtures.

## Variáveis de ambiente

Todas estão documentadas em [`.env.example`](.env.example). O `.env` é carregado com
python-dotenv, se existir. Variáveis já definidas no ambiente têm precedência.

| Variável | Padrão | Observação |
|---|---|---|
| `DEBUG` | `False` | `True` apenas em desenvolvimento |
| `SECRET_KEY` | — | **Obrigatória** com `DEBUG=False` |
| `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` | vazio (`localhost,127.0.0.1` com DEBUG) | Listas separadas por vírgula |
| `SQLITE_PATH` | `<projeto>/db.sqlite3` | Fora de `public_html` |
| `SQLITE_JOURNAL_MODE` | `WAL` | `DELETE` se o banco estiver em NFS |
| `STATIC_ROOT` / `MEDIA_ROOT` | `<projeto>/staticfiles` / `<projeto>/media` | |
| `LOG_DIR` | `<projeto>/logs` | Log rotativo `app.log` (só com DEBUG=False) |
| `SECURE_SSL_REDIRECT` | `True` | Só com DEBUG=False |
| `SECURE_HSTS_SECONDS` | `0` | Ativar depois de confirmar HTTPS estável |
| `SOULMV_EXTRATOR` | `arquivo_local` | Origem do CSV usada pelo job |
| `SOULMV_INBOX_DIR` | — | Obrigatória para o job; fora de `public_html` (LGPD) |
| `SOULMV_LOCK_FILE` | `<INBOX>/.job_pacientes_soulmv.lock` | |
| `SOULMV_RETENCAO_DIAS` | `7` | CSVs mais antigos são apagados do inbox |
| `SOULMV_USUARIO` / `SOULMV_SENHA` | — | Conta MV (Fase 2) |

## Produção (cPanel / Passenger)

- Startup file: `passenger_wsgi.py`, que aponta para `ambulatorio.wsgi.application`.
- `python manage.py migrate` e `python manage.py collectstatic --noinput` a cada deploy.
- Static servido pelo WhiteNoise (`CompressedManifestStaticFilesStorage`). `MEDIA_ROOT` deve ser
  servido pelo Apache. O Django só serve media com `DEBUG=True`.
- Valide com `python manage.py check --deploy`. O único aviso esperado é `security.W004`
  (HSTS), até `SECURE_HSTS_SECONDS` ser ativado.
- O banco SQLite e `media/` são dados e não vão no git: migre-os junto com o deploy.

## Importação Soul MV

Especificação: [`docs/specs/job-importacao-soulmv.md`](docs/specs/job-importacao-soulmv.md).

Regras: **somente inserção**. Paciente já existente, encontrado por código cidadão ou CPF, não é
alterado. A exceção é o paciente manual sem código cidadão, que recebe o código para ficar vinculado.
Agendamento novo é criado inclusive para paciente existente. Reimportar o mesmo arquivo (mesmo sha256)
resulta em `ignorado`. Nada é deletado nem inativado. Toda execução fica registrada em
`ExecucaoImportacao`, visível no admin, somente leitura.

### Comandos

```bash
# Importa um CSV específico (--forcar ignora a checagem de sha256; não duplica nada)
python manage.py importar_pacientes_soulmv --arquivo /caminho/20261113080000.csv

# Job horário: lock entre processos -> limpeza do inbox (> 7 dias) -> extração
# (período hoje -> fim do mês) -> importação. Sai com código != 0 se a execução terminar em erro;
# se já houver uma execução em andamento, registra "já em execução" e sai com 0.
python manage.py job_pacientes_soulmv
```

Cron sugerido (cPanel): `0 * * * * cd ~/app && ~/virtualenv/<app>/<versão>/bin/python manage.py job_pacientes_soulmv`

### API (Plano C)

`POST /api/integracao/soulmv/importar/`: JWT (`Authorization: Bearer <token>`) de usuário **staff**,
multipart com o campo `arquivo` (até 10 MB).

| Resposta | Situação |
|---|---|
| 200 | `sucesso` ou `ignorado` |
| 422 | `erro` (ex.: cabeçalho inválido) |
| 409 | Importação ou job em andamento |
| 413 | Arquivo grande demais |
| 401 / 403 | Sem token / usuário não-admin |

```bash
TOKEN=$(curl -s -X POST https://seu-dominio/api/token/ -d username=... -d password=... | jq -r .access)
curl -H "Authorization: Bearer $TOKEN" -F arquivo=@20261113080000.csv https://seu-dominio/api/integracao/soulmv/importar/
```

## Estrutura

- `ambulatorio/`: settings (por env), `settings_test.py`, urls, wsgi
- `core/`: modelos, views (site e API), admin, templates de documento
- `core/integracao/soulmv/`: `leitor` (CSV), `importador` (insert-only), `periodo`, `extrator`, `lock`, `job`
- `core/management/commands/`: `importar_pacientes_soulmv`, `job_pacientes_soulmv`
- `core/tests/`: testes pytest e fixtures sintéticas
- `static/`: CSS, JS e modelos-base de documentos (`templates_documentos/`, `Texto/`)
- `templates/`: templates HTML

Veja também o [CHANGELOG](CHANGELOG.md).
