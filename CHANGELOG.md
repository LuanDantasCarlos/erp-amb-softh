# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).

## [Não lançado]

### Deploy cPanel HostGator (13/11/2026)

#### Adicionado
- `deploy/cpanel/index.fcgi` e `deploy/cpanel/htaccess`: execução via Apache `mod_fcgid` + flup,
  porque o servidor compartilhado não tem `mod_passenger`. Dependência `flup==1.0.3`.
- Produção em `https://ambulatorio.softh.com.br` (Python 3.12 instalado com `uv` na pasta do usuário;
  SQLite em `~/ambulatorio_data`).

#### Alterado
- `passenger_wsgi.py` reexecuta com o `.venv` do projeto, porque o Passenger do cPanel usa o Python do sistema.

### Fase 1 — Importador CSV Soul MV

#### Adicionado
- `Paciente`: campos `codigo_cidadao` (único), `cns`, `nome_social` e `origem` (`manual`/`soulmv`).
- Modelos `Agendamento` (paciente `PROTECT`, `solicitacao` única) e `ExecucaoImportacao` (log/auditoria
  com status `executando`/`sucesso`/`erro`/`ignorado`). Migração `0005_importacao_soulmv`.
- `core/integracao/soulmv/leitor.py`: leitura do CSV com encoding utf-8-sig e fallback cp1252.
  Valida o cabeçalho, normaliza o CPF (`zfill(11)` → `000.000.000-00`, vazio → `NULL`), CNS e datas.
  Linha inválida é rejeitada sozinha, com motivo e sem expor dados pessoais.
- `core/integracao/soulmv/importador.py`: importação insert-only em `transaction.atomic` com `bulk_create`.
  Idempotente por sha256. Vincula `codigo_cidadao` a paciente manual encontrado por CPF.
- `core/integracao/soulmv/periodo.py`: período de hoje até o último dia do mês.
- Command `importar_pacientes_soulmv --arquivo <csv> [--forcar]`.
- Testes pytest com CSVs sintéticos.

#### Alterado
- `Paciente.cpf`, `sexo` e `celular` passam a aceitar nulo. No `PacienteForm`, CPF vazio vira `NULL`;
  CPF preenchido continua com validação de dígito verificador.
- Templates exibem "Não informado"/"-" em vez de `None`.
- `core/tests.py` movido para `core/tests/tests_legado.py`. Esses testes já falhavam antes, porque
  usam os campos inexistentes `cidade`/`estado`, e não são coletados pelo pytest.

### Fase 3 — Orquestração

#### Adicionado
- SQLite com `timeout=30` e `journal_mode` configurável (`SQLITE_JOURNAL_MODE`, padrão WAL).
- `extrator.py`: Protocol `Extrator` e `ExtratorArquivoLocal` (CSV mais recente de uma pasta).
- `lock.py`: lock entre processos por arquivo (`O_CREAT|O_EXCL`, PID + timestamp). Lock com mais
  de 50 min é considerado morto.
- `job.py` + command `job_pacientes_soulmv`:
  - lock;
  - marca como erro execuções presas há mais de 50 min;
  - limpa CSVs do inbox com mais de 7 dias;
  - extrai e importa;
  - sai com código ≠ 0 quando a execução termina em erro.
- `POST /api/integracao/soulmv/importar/` (Plano C): JWT + `IsAdminUser`, limite de 10 MB, compartilha
  o lock do job (responde 409 se estiver ocupado).
- Admin: `Agendamento` e `ExecucaoImportacao` (somente leitura). Fieldset "Soul MV" em `Paciente`.

#### Alterado
- `DELETE /api/pacientes/<id>/` de paciente com agendamentos responde 409 em vez de 500.
- Erro de persistência na importação grava só o tipo da exceção (LGPD); detalhes vão para o log.

### Fase 4 — Preparação para produção (código)

#### Adicionado
- Settings por variável de ambiente, com `.env` opcional via python-dotenv; ver `.env.example`.
- `DEBUG` com padrão `False`. `SECRET_KEY` é obrigatória fora de DEBUG.
- `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` vêm de env, sem `*` e sem domínios do Replit.
- `SQLITE_PATH`, `STATIC_ROOT`, `MEDIA_ROOT`, `LOG_DIR` configuráveis.
- Com `DEBUG=False`:
  - `SECURE_PROXY_SSL_HEADER`, `SECURE_SSL_REDIRECT`, cookies seguros e HSTS configurável;
  - log rotativo em `LOG_DIR/app.log`;
  - `DisallowedHost` silenciado.
- WhiteNoise (`CompressedManifestStaticFilesStorage`).
- `passenger_wsgi.py` para o Application Manager do cPanel.
- `ambulatorio/settings_test.py` (usado pelo pytest) e `requirements-dev.txt`.

#### Alterado
- `django-debug-toolbar` (app, middleware e urls) só é ativado com `DEBUG=True` e se estiver instalado.
- `requirements.txt`:
  - convertido de UTF-16 para UTF-8;
  - removidos `oracledb`, `cryptography`, `cffi` e `pycparser` (só eram usados pelo oracledb);
  - removido `rest-framework-simplejwt==0.0.2` (pacote errado);
  - `django-debug-toolbar` foi para o dev;
  - adicionados `whitenoise`, `python-dotenv`, `requests` (e dependências);
  - validado em Python 3.10.

#### Removido do controle de versão
Os arquivos continuam no disco e agora estão no `.gitignore`:
- `sistema_ambulatorial.tar.gz`;
- `media/`, PDFs de template enviados por usuários (são dados);
- `templates/*/*.pdf`, cópias de upload gravadas pelo serializer.

### Conhecido / a fazer
- `core/serializers.py:29` e `core/serializers.py:41`: `TemplateDocumentoSerializer` copia o PDF para
  `templates/<user_id>/` **relativo ao cwd**. No Passenger o cwd é imprevisível, e o upload pode cair
  dentro do diretório de código. Deve gravar em `MEDIA_ROOT`.
- Fase 2: cliente HTTP do Soul MV (`cliente_http.py`), que depende do login do usuário.
- Alerta por e-mail em falha do job.
- `drf_yasg` emite `DeprecationWarning` (`SWAGGER_USE_COMPAT_RENDERERS`).
- `PyPDF2` está descontinuado. Migrar para `pypdf`.
- `SIMPLE_JWT['BLACKLIST_AFTER_ROTATION']=True` não tem efeito: o app `token_blacklist` não está instalado.
