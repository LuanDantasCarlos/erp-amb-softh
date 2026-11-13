# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).

## [Não lançado]

### Templates de documentos de oftalmologia

#### Adicionado
- Models `Medico` (CNS/CPF normalizados, `assinatura`, FK opcional para `User`) e `Procedimento` (SIGTAP).
  `Documento.medico` e `Documento.data_atendimento` (nullable). Migração aditiva `0006`.
- Command `importar_procedimentos_sigtap [--csv]`: upsert por código. O padrão é o CSV do repositório
  (146 procedimentos).
- Command `instalar_templates_oftalmo` (idempotente): gera os PDFs base em `MEDIA_ROOT/templates/oftalmologia/`
  e cria ou atualiza os templates e campos pelo nome.
  - Campo que saiu do layout é excluído; se já foi preenchido em algum documento, é só inativado.
  - Desativa "Receituario Colirio - Timolol" se ele não tiver documentos emitidos.
- Layouts por código (`core/documentos/layouts/`): BPA-I, Prescrição de Óculos e Receituário de Colírios
  2 vias (A4 paisagem).
- `core/documentos/fontes.py`: `resolver_valor` com prefixos `paciente.`, `medico.`, `estabelecimento.`,
  `atendimento.` e `sistema.`. Sem prefixo, a chave continua sendo atributo do paciente.
- Settings `ESTABELECIMENTO_NOME/CNES/NUCLEO/UNIDADE`.
- Engine (`core/documentos/engine.py`):
  - tipo `procedimentos`: uma página por procedimento marcado, com QTD;
  - tipo `radio`;
  - checkbox com várias posições por opção (2 vias) e `implica` (OD/OE marcam o medicamento);
  - texto com `width` reduz a fonte até 7pt e corta sem estourar a caixa;
  - `align`, texto multilinha, `validacoes.padrao` e `validacoes.copiar_de`.
- Gerar documento:
  - selects Médico e Data do atendimento;
  - endpoint `valores_automaticos`: campos automáticos pré-preenchidos e editáveis;
  - lista de procedimentos agrupada, com busca.
  - Médico pré-selecionado: o ligado ao usuário; senão o último usado na sessão.

#### Alterado
- select/radio imprimem o **texto** da opção (antes imprimiam o id).
- Datas automáticas saem em `dd/mm/aaaa` também nos templates antigos (antes `aaaa-mm-dd`).
- Campo apagado de propósito no formulário fica vazio no PDF (antes voltava o valor do paciente).
- `CampoPreenchidoDocumento` grava o valor final usado no PDF, já com os automáticos; listas e
  procedimentos em JSON.
- Erro ao gerar documento: a mensagem não expõe a exceção (fica no log), e `print` virou `logging`.
- Removido o flatpickr (CDN), que não era usado.

### Pacientes por data do atendimento

#### Adicionado
- Lista de pacientes:
  - filtro **Data do atendimento** (`?data=AAAA-MM-DD`) com atalhos Hoje/Amanhã. Mostra só quem tem
    agendamento no dia local (America/Sao_Paulo), ordenado pelo primeiro horário do dia e depois pelo nome,
    sem duplicar paciente;
  - colunas **Atendimento** e **Item de agendamento**. Com o filtro, mostram o primeiro agendamento do dia;
    sem filtro, o próximo agendamento a partir de agora ou, se não houver, o último.
- Detalhe do paciente: seção **Agendamentos** (data/hora, item, solicitação), da mais recente para a mais
  antiga, com destaque para a de hoje. Mostra também CNS, código cidadão, origem e nome social.
- Gerar documento: o select de pacientes mostra "atendimento hoje HH:MM" quando o paciente tem
  agendamento no dia.
- `core/agenda.py`: subqueries correlacionadas sobre o índice `(paciente, data_agenda)`.
  - A lista faz um número constante de queries (testado com `django_assert_num_queries`).
  - O dia é filtrado por intervalo `[00:00, 00:00 do dia seguinte)`, e não por `__date`, para usar o índice.

#### Alterado
- Busca da lista aceita também CNS, código cidadão, nome social e CPF digitado sem máscara.
- Paginação: 25 por página, mantendo todos os filtros na querystring, que agora é escapada.
- Removidos da lista o filtro "Estado" e a coluna "Cidade/UF": os campos não existem no modelo e
  apareciam sempre vazios.

### Fase 2 — Cliente HTTP do Soul MV

#### Adicionado
- `core/integracao/soulmv/cliente_http.py`: `ClienteSoulMV` com:
  - `login()`: CAS com redirects manuais e token do fragmento `#access_token=`;
  - `descobrir_contexto()`: user, perfil, company, vínculo e unidade executante descobertos por descrição;
  - `listar(inicio, fim)`: header `MVFor-Profile`, período em UTC, timeout de 240 s.
- `ExtratorHttpSoulMV`, registrado como `SOULMV_EXTRATOR=http`. Grava `soulmv_<timestamp>.csv` no inbox.
- `core/integracao/soulmv/exportacao_csv.py`: `registros_para_csv`, o mesmo CSV do export da tela.
- Settings `SOULMV_API_URL`, `SOULMV_PERFIL`, `SOULMV_UNIDADE_SOLICITANTE` e `SOULMV_UNIDADE_EXECUTANTE`.
- Erros de login/rede/HTTP viram `ExtracaoError` sem senha, token ou URL com ticket. Senha expirada gera alerta próprio.
- Testes 100% mockados (o MV só é alcançável a partir do servidor).

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
- Importar `sexo` e `nomeMae`, que vêm no JSON do Soul MV mas não no CSV da tela.
  O campo "Nome da Mãe" do BPA-I já usa `paciente.nome_mae` e passa a ser preenchido sozinho quando
  o atributo existir.
- Salvar a resposta/HTML da falha de extração para diagnóstico (spec, Fase 2).
- Alerta por e-mail em falha do job.
- `drf_yasg` emite `DeprecationWarning` (`SWAGGER_USE_COMPAT_RENDERERS`).
- `PyPDF2` está descontinuado. Migrar para `pypdf`.
- `SIMPLE_JWT['BLACKLIST_AFTER_ROTATION']=True` não tem efeito: o app `token_blacklist` não está instalado.
