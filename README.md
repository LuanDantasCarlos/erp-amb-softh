# Sistema de Gerenciamento Ambulatorial

Sistema ambulatorial em Django + Django REST Framework para cadastro de pacientes e emissão de
documentos médicos em PDF a partir de templates. Os pacientes e agendamentos novos são importados de
hora em hora do export da Central de Marcação do Soul MV.

## Funcionalidades

- Cadastro de pacientes: manual ou importado do Soul MV, nunca sobrescrito pela importação
- Localização de pacientes pela data do atendimento: filtro na lista (`/pacientes/?data=AAAA-MM-DD`, atalhos
  Hoje/Amanhã), colunas de atendimento e item de agendamento, e histórico de agendamentos no detalhe.
  Busca por nome, CPF (com ou sem máscara), CNS, código cidadão ou e-mail.
- Templates de documento em PDF com campos posicionados e preenchimento automático (paciente, médico,
  estabelecimento, data do atendimento), sempre editável antes de gerar
- Documentos de oftalmologia gerados por código: BPA-I (um por procedimento SIGTAP marcado), Prescrição de
  Óculos e Receituário de Colírios em 2 vias
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
| `SOULMV_EXTRATOR` | `arquivo_local` | Origem do CSV usada pelo job: `http` (cliente do Soul MV, produção) ou `arquivo_local` |
| `SOULMV_INBOX_DIR` | — | Obrigatória para o job; fora de `public_html` (LGPD) |
| `SOULMV_LOCK_FILE` | `<INBOX>/.job_pacientes_soulmv.lock` | |
| `SOULMV_RETENCAO_DIAS` | `7` | CSVs mais antigos são apagados do inbox |
| `SOULMV_USUARIO` / `SOULMV_SENHA` | — | Conta MV; obrigatórias com `SOULMV_EXTRATOR=http` |
| `SOULMV_API_URL` | `https://regulacao.saude.es.gov.br/consultas-exames/api/` | |
| `SOULMV_PERFIL` | `COORDENADOR DE UNIDADE CMCE` | Descrição do perfil (casada sem diferenciar caixa/espaços) |
| `SOULMV_UNIDADE_SOLICITANTE` | `NUCLEO ESPECIAL DE REGULACAO DE CONSULTAS E EXAMES` | Estabelecimento do vínculo (company) |
| `SOULMV_UNIDADE_EXECUTANTE` | `RCS SOLUCOES MEDICAS S/A` | Nome exato; as variantes por município não casam |
| `ESTABELECIMENTO_NOME` / `_CNES` | `CRE- METROPOLITANO` / `5604613` | Impressos nos documentos |
| `ESTABELECIMENTO_NUCLEO` / `_UNIDADE` | `Núcleo Regional de Especialidade de Vitória` / `Unidade de Oftalmologia` | |

## Produção (cPanel HostGator — FastCGI)

O servidor compartilhado não tem `mod_passenger` (o "Application Manager" aparece no cPanel,
mas não funciona). A aplicação roda via **Apache `mod_fcgid` + flup**:

| Item | Local no servidor |
|---|---|
| URL | `https://ambulatorio.softh.com.br` |
| Código + venv (Python 3.12 via `uv`) | `~/apps/erp-amb-softh` (`.venv`, `.env` com permissão 600) |
| Document root | `~/ambulatorio_public` (`index.fcgi` + `.htaccess`, copiados de `deploy/cpanel/`) |
| Dados (SQLite, media, inbox, logs, static) | `~/ambulatorio_data` |

Deploy de uma nova versão (via SSH, porta 2222):

```bash
cd ~/apps/erp-amb-softh && git pull
~/.local/bin/uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python manage.py migrate --noinput && .venv/bin/python manage.py collectstatic --noinput
cp deploy/cpanel/index.fcgi ~/ambulatorio_public/index.fcgi && chmod 755 ~/ambulatorio_public/index.fcgi
touch ~/ambulatorio_public/index.fcgi   # o mod_fcgid recarrega o processo
```

- `passenger_wsgi.py` fica para hosts com Passenger; ele se reexecuta com o `.venv` (o Passenger usa o Python do sistema).
- `python manage.py migrate` e `python manage.py collectstatic --noinput` a cada deploy.
- Static servido pelo WhiteNoise (`CompressedManifestStaticFilesStorage`). `MEDIA_ROOT` deve ser
  servido pelo Apache. O Django só serve media com `DEBUG=True`.
- Valide com `python manage.py check --deploy`. O único aviso esperado é `security.W004`
  (HSTS), até `SECURE_HSTS_SECONDS` ser ativado.
- O banco SQLite e `media/` são dados e não vão no git: migre-os junto com o deploy.

## Documentos de oftalmologia

Especificação: [`docs/specs/templates-oftalmologia.md`](docs/specs/templates-oftalmologia.md).

```bash
python manage.py importar_procedimentos_sigtap          # 146 procedimentos (SIGTAP 11/2026), upsert por código
python manage.py instalar_templates_oftalmo             # (re)gera os PDFs base e os campos; idempotente
```

- Médicos: cadastrar no admin (`Médico`), ligando ao `Usuário` quando o médico emite os próprios documentos.
  Nunca versionar dados de médicos.
- Layouts em `core/documentos/layouts/` (reportlab): o mesmo código desenha o PDF base e devolve as posições.
  Depois de mudar um layout, rode `instalar_templates_oftalmo` de novo.
- Fontes automáticas em `CampoTemplateDocumento.atributo_paciente`: `paciente.<attr>` (ou só `<attr>`),
  `paciente.nascimento_curto`, `paciente.telefone_contato`, `medico.<attr>`, `medico.assinatura`,
  `estabelecimento.nome|cnes|nucleo|unidade`, `atendimento.data|mes_ano`, `sistema.hoje`.
  `validacoes` aceita `padrao` (valor inicial) e `copiar_de` (nome de outro campo).
- Gerar documento: selects de Médico (obrigatório quando o template usa `medico.*`) e Data do atendimento
  (padrão: agendamento de hoje, senão o próximo, senão hoje). Os campos automáticos chegam preenchidos
  (`/valores_automaticos/`) e o valor digitado sempre vence.

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

### Extração HTTP (`SOULMV_EXTRATOR=http`)

`core/integracao/soulmv/cliente_http.py` reproduz o front sem navegador:

1. login no CAS (`oauth2/login` → formulário → redirects seguidos à mão até `#access_token=`);
2. descoberta dos ids em runtime (`usuario/currentUser`, lista de perfis e de vínculos), casando pelas
   descrições configuradas;
3. `GET solicitacao-procedimento/solicitacoes-consulta-regulador-com-vinculos` com `tipoData=1` (agendamento),
   período hoje 00:00 → último dia do mês 00:00 (America/Sao_Paulo, enviado em UTC) e o header `MVFor-Profile`;
4. `exportacao_csv.registros_para_csv` gera o mesmo CSV da tela, gravado como `soulmv_<timestamp>.csv` no inbox
   (permissão 0600) e importado pelo mesmo importador.

Falhas (credencial errada, senha expirada, perfil/unidade não encontrados, HTTP ≠ 200) viram execução com
`erro` em `ExecucaoImportacao`. Senha, token e ticket do CAS nunca aparecem em mensagem ou log.

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
- `core/integracao/soulmv/`: `cliente_http` (Soul MV), `exportacao_csv`, `leitor` (CSV), `importador` (insert-only),
  `periodo`, `extrator`, `lock`, `job`
- `core/documentos/`: `fontes` (valores automáticos), `engine` (overlay), `layouts/` (BPA-I, prescrição,
  receituário), `instalacao`, `sigtap`, `formulario`; `assets/` (logos) e `dados/` (CSV do SIGTAP)
- `core/management/commands/`: `importar_pacientes_soulmv`, `job_pacientes_soulmv`,
  `importar_procedimentos_sigtap`, `instalar_templates_oftalmo`
- `core/tests/`: testes pytest e fixtures sintéticas
- `static/`: CSS, JS e modelos-base de documentos (`templates_documentos/`, `Texto/`)
- `templates/`: templates HTML

Veja também o [CHANGELOG](CHANGELOG.md).
