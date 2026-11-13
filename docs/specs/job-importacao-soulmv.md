# Spec — Job de importação de pacientes (Soul MV → ERP Ambulatorial)

Status: **aprovada — Fase 1 liberada** · Decisões fechadas em 13/11/2026 (§6)

## 1. Contexto

O acesso direto à view do Soul MV foi limitado. A base passa a ser obtida pelo export da tela
**Central de Marcação de Consultas e Exames** (Soul MV Regulação — SESA/ES), de hora em hora,
importando **pacientes novos** e seus **agendamentos** para emissão de documentos.

Destino de produção: **cPanel HostGator** (deploy conduzido pelo coordenador; o usuário só faz login).

Fonte do mapeamento: gravação de tela de 12/11/2026 (processo manual, ~3 min, sem áudio).

## 2. Processo manual mapeado (as-is)

| # | Passo | Detalhe para automação |
|---|-------|------------------------|
| 1 | Acessar o sistema | `https://regulacao.saude.es.gov.br/consultas-exames/` |
| 2 | Login SSO (CAS "Autenticador SSO" MV) | **Usuário** / **Senha** → **ENTRAR**. Sem captcha/MFA observados. Após o login, a URL traz `#/login?access_token=AT-...` (fluxo CAS → OAuth2) |
| 3 | Seleção de perfil | `COORDENADOR DE UNIDADE CMCE` + `NUCLEO ESPECIAL DE REGULACAO DE CONSULTAS E EXAMES` → **Entrar** |
| 4 | Tela de listagem | Rota `#/recepcao/solicitacao-listagem` |
| 5 | **Unidade executante** | Autocomplete: digitar `RCS SOLUCOES` e escolher **exatamente** `RCS SOLUCOES MEDICAS S/A` (não as variantes por município, ex. `FUNDAO - RCS ...`) |
| 6 | **Tipo de data** | `AGENDAMENTO` (default é `SOLICITAÇÃO`) |
| 7 | **Período** | **hoje → último dia do mês corrente** |
| 8 | Demais filtros | Default (Situação = "27 situações selecionadas"; Unidade solicitante vem do perfil) |
| 9 | Pesquisar (lupa) | Loading ~20 s. Rodapé `TOTAL: N` (~4.100 no vídeo) |
| 10 | Exportar (ícone planilha, à direita da impressora) | Toast "Exportação de solicitações…". Download `yyyyMMddHHmmss.csv` (~1,2 MB) |
| 11 | Excel (manual) | **Não reproduzir.** O Excel remove zeros à esquerda do CPF (`00351074643` → `351074643`). O job lê o CSV direto |

## 3. Layout do CSV exportado

- Separador `,` · cabeçalho na linha 1 · **vírgula sobrando no fim do cabeçalho** (coluna vazia — descartar)
- Encoding não confirmado: tentar `utf-8-sig`, fallback `cp1252`
- Datas `dd/mm/aaaa`; com hora `dd/mm/aaaa HH:MM`
- **Uma linha por solicitação** — paciente se repete
- Ler **tudo como string** (`dtype=str, keep_default_na=False`)

Colunas (21): `Solicitação, Unidade solicitante, Código cidadão, CNS do cidadão, CPF do cidadão,
Nome social, Nome do cidadão, Data Nascimento, Data da solicitação, Item agendamento,
Unidade executante, Profissional executante, Data da agenda, Data de marcação, Situação, Motivo,
Emissão guia, Data da marcação original, Marcado por, T. solicitação, Prioridade`

| Coluna CSV | Exemplo (sintético) | Destino |
|---|---|---|
| Código cidadão | `1234567` | `Paciente.codigo_cidadao` — **chave** |
| CNS do cidadão | `700000000000001` | `Paciente.cns` |
| CPF do cidadão | `00012345678` | `Paciente.cpf` → `000.123.456-78` |
| Nome social | (geralmente vazio) | `Paciente.nome_social` |
| Nome do cidadão | `FULANO DE TAL` | `Paciente.nome` |
| Data Nascimento | `01/02/1950` | `Paciente.data_nascimento` |
| Solicitação | `8000001` | `Agendamento.solicitacao` — **chave** |
| Item agendamento | `CONSULTA EM OFTALMOLOGIA GLAUCOMA ADULTO METROPOLITANA` | `Agendamento.item_agendamento` |
| Data da agenda | `13/11/2026 08:06` | `Agendamento.data_agenda` |
| demais colunas | | ignoradas |

## 4. Modelo de dados

### 4.1 `Paciente` (`core/models.py:20`) — migração

O export **não traz** `sexo`, `celular`, `rg`, `telefone`, `email`; hoje `sexo` e `celular` são obrigatórios.

- `codigo_cidadao = CharField(max_length=20, unique=True, null=True, blank=True)`
- `cns = CharField(max_length=15, null=True, blank=True, db_index=True)`
- `nome_social = CharField(max_length=255, null=True, blank=True)`
- `cpf`: `null=True, blank=True`, mantendo `unique=True` (gravar `None`, nunca `""`)
- `sexo`, `celular`: `null=True, blank=True` (ajustar `PacienteForm` e templates que assumem valor)
- `origem = CharField(choices=[('manual','Manual'),('soulmv','Soul MV')], default='manual')`

### 4.2 `Agendamento` — novo

```python
class Agendamento(BaseModel):
    paciente = models.ForeignKey(Paciente, on_delete=models.PROTECT, related_name='agendamentos')
    solicitacao = models.CharField(max_length=20, unique=True)
    item_agendamento = models.CharField(max_length=255)
    data_agenda = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-data_agenda']
        indexes = [models.Index(fields=['paciente', 'data_agenda'])]
```

### 4.3 Regras de importação — **somente inserção**

- **Paciente**: existe se casar por `codigo_cidadao` **ou** por CPF. Se existir → **não altera nada**
  (exceção: paciente manual casado por CPF sem `codigo_cidadao` → grava só o `codigo_cidadao`, para vincular).
  Se não existir → cria com `origem='soulmv'`.
- **Agendamento**: cria se `solicitacao` ainda não existir, **inclusive para pacientes que já existiam**
  (um paciente pode ter vários agendamentos). Agendamento existente não é alterado.
- Nada é deletado nem inativado. `Documento.paciente` é `CASCADE` (`core/models.py:204`).
- Não renomear atributos de `Paciente`: são o contrato de `atributo_paciente` (`core/utils.py:99`).
- Linha sem `Código cidadão` e sem CPF → rejeitada (sem como deduplicar).

### 4.4 `ExecucaoImportacao` — log/auditoria

`iniciado_em, finalizado_em, status (sucesso/erro/ignorado), arquivo, sha256, linhas_lidas,
pacientes_criados, agendamentos_criados, linhas_rejeitadas, detalhes_rejeicao (JSON), erro (texto)`

## 5. Arquitetura

```
core/integracao/soulmv/
├── cliente_http.py    login CAS/OAuth + filtro + export via HTTP (requests) — alvo de produção
├── extrator_rpa.py    Playwright, mesmo fluxo pela UI — descoberta/plano B (não roda no cPanel compartilhado)
├── leitor.py          CSV → registros validados (cabeçalho, normalização CPF/CNS/datas)
├── importador.py      insert-only Paciente + Agendamento em transaction.atomic, bulk_create
└── models.py          ExecucaoImportacao
core/management/commands/
├── importar_pacientes_soulmv.py   --arquivo <csv>
└── job_pacientes_soulmv.py        extrai (http|rpa) + importa, com lock
```

### Restrições do cPanel HostGator (definem a arquitetura)
- Hospedagem compartilhada (CloudLinux): **sem root, limites de RAM/processos** → Chromium headless provavelmente não roda. Por isso a extração de produção deve ser **HTTP puro**.
- Python via "Setup Python App" (Passenger). Django 5.2 exige **Python ≥ 3.10** — verificar versão disponível.
- Banco: MySQL/MariaDB do cPanel (Django 5.2 exige MySQL ≥ 8.0.11 / MariaDB ≥ 10.5) ou PostgreSQL se o plano oferecer. Driver: `PyMySQL` se `mysqlclient` não compilar.
- Cron do cPanel: `0 * * * * cd ~/app && ~/virtualenv/.../python manage.py job_pacientes_soulmv`.
- **Rede**: confirmar que o servidor alcança `regulacao.saude.es.gov.br` (sites gov podem bloquear IP estrangeiro).

**Plano C — aprovado pelo usuário como fallback** (se o HTTP puro for inviável **e** o servidor não rodar Chromium, ou o IP for bloqueado):
o extrator roda numa máquina Windows local (Agendador de Tarefas) e envia o CSV para
`POST /api/integracao/soulmv/importar/` (JWT, já existe `simplejwt`) no servidor. O importador é o mesmo.

### Requisitos não funcionais
- **Idempotente**: mesmo sha256 da última execução com sucesso → `ignorado`. Insert-only já garante que reimportar não duplica.
- **Lock** contra execução sobreposta; execução > 50 min = falha.
- **Validação de layout**: cabeçalho divergente → aborta sem gravar.
- **Sanidade**: CSV com 0 linhas → `erro` (filtro errado / sessão caiu), não `sucesso`.
- **Linha inválida não derruba o lote**: rejeita e registra motivo.
- **Credenciais** em env (`SOULMV_USUARIO`, `SOULMV_SENHA`, `SOULMV_INBOX_DIR`) — nunca no código.
- **LGPD**: CSV tem CPF/CNS/nome. `INBOX_DIR` fora de `public_html`/`MEDIA_ROOT`/`static`, no `.gitignore`, retenção 7 dias. Não logar CPF completo.

## 6. Decisões (fechadas em 13/11/2026)

| # | Decisão |
|---|---------|
| 1 | Conta MV para o job: **já existe** (credenciais vão para env no servidor, informadas pelo usuário) |
| 2 | Período: **sempre hoje → fim do mês**. Importa **somente pacientes que ainda não existem** |
| 3 | Guardar `Agendamento` (paciente + item de agendamento); paciente pode ter N agendamentos |
| 4 | Ninguém é inativado/deletado pelo job |
| 5 | Deploy em **cPanel HostGator**, conduzido pelo coordenador; usuário só faz login |
| 6 | Sem `.xls`; o CSV é só insumo de importação |
| 7 | Fallback aprovado: extrator rodando numa máquina Windows separada, enviando o CSV ao servidor (Plano C, §5) |

## 7. Plano de entrega

**Fase 0 — Go/no-go do servidor** (coordenador, assim que houver login no cPanel)
- Tipo de plano (compartilhado × VPS), SSH/Terminal, versões de Python e MySQL/PostgreSQL
- `curl -I https://regulacao.saude.es.gov.br/consultas-exames/` a partir do servidor
- Resultado define: HTTP no servidor · RPA no servidor (VPS) · Plano C

**Fase 1 — Importador** (dev, pode começar já)
- Migrações §4 · `leitor.py` · `importador.py` · command `importar_pacientes_soulmv --arquivo`
- Testes pytest com CSV **sintético** em `core/tests/fixtures/` (nunca dados reais)

**Fase 2 — Extração**
- 2a. Spike (Playwright local, `--headed`, captura de rede/HAR): mapear login CAS → OAuth2 → token, seleção de perfil, endpoint de pesquisa/export e seus parâmetros (unidade executante, tipo de data, período, situações)
- 2b. `cliente_http.py` reproduzindo o fluxo com `requests.Session` (preferencial)
- 2c. `extrator_rpa.py` só se 2b for inviável
- Falha → salvar resposta/HTML (e screenshot no RPA) para diagnóstico

**Fase 3 — Orquestração**
- `job_pacientes_soulmv` (lock, idempotência, sanidade), alerta por e-mail em falha

**Fase 4 — Hardening + deploy** (coordenador)
- `settings` por env: `DEBUG=False`, `SECRET_KEY`, `ALLOWED_HOSTS`, `DATABASES`; `debug_toolbar` só com DEBUG
- `requirements.txt` hoje está em **UTF-16** → converter para UTF-8; incluir driver do banco e `requests`
- Static via `collectstatic` (whitenoise ou pasta servida pelo Apache) · `passenger_wsgi.py`
- Migrar dados do SQLite atual (templates/campos cadastrados) para o banco do cPanel
- Cron horário · atualizar README e CHANGELOG

### Fase 2 — mapeamento estático do Soul MV (13/11/2026, feito a partir do servidor)

Fonte: bundle Angular público (`main`, `vendor`, chunks `6` e `80`) e
`/consultas-exames/assets/environments/config.production.json`. Ainda não validado com login.

**Config:** `auth.type=OAUTH2`, `authenticationFlow=AUTHORIZATION_CODE`, `modulo=4`,
`backPath=/consultas-exames/api/`, `oAuth2Path=/consultas-exames/api/oauth2`.

**Login (a confirmar no spike):**
1. `GET /consultas-exames/api/oauth2/login` → `204` com `Location:`
   `/public-health-sso/oauth2.0/authorize?response_type=token&client_id=consultasExamesOauth&redirect_uri=https://regulacao.saude.es.gov.br/consultas-exames/#/login&state=…&code_challenge=…&code_challenge_method=S256`
2. CAS (Apereo) em `/public-health-sso/login`: formulário com `username`, `password`, `execution`, `_eventId=submit`
3. Retorno para `…/consultas-exames/#/login?access_token=AT-…` (o vídeo mostra isso na URL). O front também tem `GET oauth2/token?code=…`
4. Seleção de perfil: o front monta `base64(JSON{user, profile, company, professionalBond})` (`getProfileToken`) e envia em **todas** as requisições no header `authorizationService.MVFOR_PROFILE` (o nome exato precisa ser confirmado)

**Listagem/export:** `GET /consultas-exames/api/solicitacoes-consulta-regulador-com-vinculos?<filtro>`
com `Authorization: Bearer <access_token>` + header de perfil. Devolve um array JSON; o próprio front monta o CSV
(BOM UTF-8, aspas só quando há vírgula, vírgula sobrando no fim da linha). Ou seja: **o export é client-side**.

Filtro (`criarFiltro`, query string sem nulos): `idUnidadeExecutante`, `tipoData`, `periodoInicial`/`periodoFinal`
(`Date.toISOString()` → **UTC**; 00:00 BRT = 03:00Z), `listaSituacoes` (ids; o default da tela tem 27), `prioridade` (5 = todas),
`tipoSolicitacao`, `idEstabelecimento`/`idUnidadeSolicitante`, além de flags (`apenasUnidadeEspecifica`, `flagRealizadoForaRede`, …).

Campos JSON → colunas do CSV (chunk 80, `corpoExportaCsv`):

| Coluna | Campo JSON |
|---|---|
| Solicitação | `idSolicitacaoProcedimento` |
| Unidade solicitante | `nomeUnidadeSolicitante` (trim) |
| Código cidadão | `idCidadao` |
| CNS do cidadão | `numeroCartaoSus` |
| CPF do cidadão | `cpf` |
| Nome social | `nomeCidadaoSocial` |
| Nome do cidadão | `nomeCidadao` |
| Data Nascimento | `nascimento` (dd/mm/aaaa) |
| Data da solicitação | `dataSolicitacao` |
| Item agendamento | `descricaoItemAgendamento` |
| Data da agenda | `flagRealizadoForaRede ? dataAtendimento : dataAgenda` (dd/mm/aaaa HH:MM) |
| demais | `nomeProfExecPorSit`, `dataMarcacao`, `situacao`, `descricaMotivoProcedNaoRealiz`, `flagEmissaoGuia`, `dataMarcacaoOriginal`, `marcadoPor`, `tipoSolicitacao`, `descricaoPrioridade` |

**Decisão de implementação:** o cliente HTTP gera **o mesmo CSV** que o front gera (mesmas 21 colunas e formatação)
e o entrega ao `importar_arquivo`. Assim o leitor, a idempotência por sha256 e a auditoria continuam iguais.

### Fase 2 — spike com login (13/11/2026, executado no servidor) — CONFIRMADO

Fluxo validado com `requests` (sem navegador), do servidor HostGator:

1. `GET {API}oauth2/login` (sem seguir redirect) → `204`, header `Location` = URL de authorize do CAS
2. `GET <Location>` (seguindo redirects) → página de login do CAS em `/public-health-sso/login?service=…`.
   Formulário: `action="login"`, `method=post`, campos `username`, `password`, `execution` (hidden), `_eventId=submit`, `geolocation` (vazio)
3. `POST` para `urljoin(url_da_pagina, "login")` com esses campos, **sem seguir redirects**. Seguir manualmente
   (`callbackAuthorize` → `authorize` (http) → `authorize` (https)) até `Location` conter
   `…/consultas-exames/#access_token=AT-…&token_type=bearer&expires_in=28800` (token válido por 8 h)
4. Sem chamada de `autorizacao/`: basta enviar em todas as requisições:
   - `Authorization: Bearer <access_token>`
   - `MVFor-Profile: base64(JSON compacto {"user":14217,"profile":57,"company":711,"professionalBond":261621})`
5. `GET {API}solicitacao-procedimento/solicitacoes-consulta-regulador-com-vinculos` com query:
   `idUnidadeExecutante=2147&tipoData=1&periodoInicial=<ISO UTC>&periodoFinal=<ISO UTC>&prioridade=5&idUnidadeSolicitante=711&idEstabelecimento=711`
   → `200`, array JSON. Hoje→30/11: **3.941 registros em ~20 s, ~6 MB**.

`API = https://regulacao.saude.es.gov.br/consultas-exames/api/`

| Parâmetro | Valor | Origem |
|---|---|---|
| user | `14217` | `GET usuario/currentUser` → `id` |
| profile | `57` (COORDENADOR DE UNIDADE CMCE) | `GET perfilUsuario/listarPerfilPorDescricaoUsuarioEModulo` |
| company | `711` (NUCLEO ESPECIAL DE REGULACAO DE CONSULTAS E EXAMES) | `GET vinculoProfissionalService/listVinculoProfissionalAtivoPorDescricaoUsuario?descUsuario=<LOGIN>&descricao=%%` |
| professionalBond | `261621` | idem (vínculo com o estabelecimento 711) |
| idUnidadeExecutante | `2147` (RCS SOLUCOES MEDICAS S/A) | idem (vínculo 260535) |
| tipoData | `1` = AGENDAMENTO (`2` = SOLICITAÇÃO, `3` = MARCAÇÃO) | chunk 80 `arrayTiposData` |
| periodoInicial/Final | 00:00 BRT de hoje / do último dia do mês, em UTC (`2026-11-13T03:00:00.000Z`) | `Date.toISOString()` do front |

- Sem `listaSituacoes`, a API devolveu as situações 5, 7 e 9. O volume bate com o vídeo (4.095 com um dia a mais).
- Os ids (user/profile/company/bond/unidade) devem ser **descobertos em runtime** pelos endpoints da tabela, casando pelas
  descrições (`COORDENADOR DE UNIDADE CMCE`, `NUCLEO ESPECIAL DE REGULACAO DE CONSULTAS E EXAMES`, `RCS SOLUCOES MEDICAS S/A`).
  Os números acima servem de fallback/validação, porque mudam se a conta mudar.
- Formatos no JSON: datas `AAAA-MM-DDTHH:MM:SS` (local, sem fuso); `cpf` com 11 dígitos sem máscara; `numeroCartaoSus` com 15 dígitos;
  `idCidadao` e `idSolicitacaoProcedimento` inteiros; `situacao` inteiro.
- O JSON também traz `sexo` e `nomeMae`, que o CSV da tela não tem.

### Critérios de aceite
- [ ] Reimportar o mesmo CSV não cria nada (status `ignorado` ou 0 criados)
- [ ] Paciente já existente (por código ou CPF) não tem nenhum campo alterado
- [ ] Novo agendamento de paciente existente é criado e vinculado a ele
- [ ] Paciente com 5 solicitações no CSV → 1 `Paciente` + 5 `Agendamento`
- [ ] CPF `00012345678` gravado como `000.123.456-78`; CPF vazio gravado como `NULL`
- [ ] Período calculado = hoje → último dia do mês (testar dia 31, 30, 28/29 de fevereiro)
- [ ] Nenhum `Paciente`/`Documento` deletado pelo job
- [ ] Cabeçalho alterado → `erro`, banco intacto
- [ ] Documento gerado para paciente importado preenche nome/CPF/data de nascimento
- [ ] Ciclo completo extração → importação < 5 min; falhas registradas em `ExecucaoImportacao`
