# Spec — Templates de documentos de Oftalmologia

Status: **aprovada para implementação** · 13/11/2026
Fonte: modelos `.docx` enviados pelo usuário (BPAI CALAZIO, PRESCRIÇÃO ÓCULOS, RECEITUÁRIO COLÍRIOS, LISTA DE COLÍRIOS)
e "Dados Médicos Oftalmologia". O `.docx` dos médicos contém **senhas de outros sistemas**: elas nunca entram no
sistema, no repositório nem em log. Só os dados cadastrais.

## 1. Objetivo

Emitir 3 documentos com o máximo de dados preenchidos automaticamente (paciente, médico, estabelecimento,
data do atendimento), usando a engine atual de overlay (`core/utils.py:gerar_documento_pdf`, PDF base +
`CampoTemplateDocumento` com posições).

## 2. Decisões de arquitetura

1. **PDFs base gerados por código** (reportlab, já é dependência), e não convertidos do `.docx`. Cada layout fica
   num módulo em `core/documentos/layouts/` que desenha o PDF base **e** devolve o mapa de posições dos campos.
   Assim as coordenadas são exatas e o layout é versionado e revisável.
2. Command idempotente `python manage.py instalar_templates_oftalmo` (re)gera os PDFs base em MEDIA e cria ou
   atualiza `TemplateDocumento` + `CampoTemplateDocumento` por **nome estável** (não duplica; não apaga
   `Documento` já emitido; campos removidos do layout são desativados ou excluídos só se não tiverem
   `CampoPreenchidoDocumento`).
3. Assets (já no repo): `core/documentos/assets/logo_sus.png`, `cabecalho_sus_es.png` (faixa SUS + Governo ES + SESA,
   do receituário) e `logo_governo_es.jpeg` (Governo do ES / Secretaria da Saúde, da prescrição).
4. Fonte: Helvetica (WinAnsi cobre acentos do PT-BR). Mesmo padrão visual dos modelos (rótulos normais,
   títulos de seção em negrito, tabelas com borda).

## 3. Novos dados e fontes de preenchimento

### 3.1 `Medico` (novo model)
`nome`, `crm` (texto livre, pode ter vários: "52295-MG / 22383-ES"), `rqe` (opcional), `cns` (15 dígitos, normalizado),
`cpf` (normalizado, opcional), `cbo` (default `225265` — médico oftalmologista), `especialidade_exibicao`
(default "Médico(a) Oftalmologista"), `ativo`, `usuario` (FK opcional para `User`, `SET_NULL`). Admin com busca.
**Não versionar dados reais de médicos** (nada de fixture com CPF/CNS): o coordenador cadastra em produção.

### 3.2 `Procedimento` (novo model)
`codigo` (formato `00.00.00.000-0`, único), `nome`, `grupo`, `instrumentos` (texto, ex. "BPA-C/BPA-I"), `ativo`.
Command `importar_procedimentos_sigtap --csv <arquivo>` (upsert por código). CSV já no repo:
`core/documentos/dados/procedimentos_oftalmo_sigtap_202611.csv` — 146 procedimentos das formas de organização
021106, 030305 e 040501–040505 do SIGTAP 11/2026 (fonte oficial DATASUS). O formulário "BPAI" funciona como
**solicitação** (tem campo do autorizador), e o próprio exemplo (exérese de calázio 04.05.01.007-9) é AIH/APAC,
por isso o catálogo não filtra pelo instrumento BPA-I; a coluna `instrumentos` fica visível na seleção.

### 3.3 Estabelecimento (settings/env, com defaults)
`ESTABELECIMENTO_NOME="CRE- METROPOLITANO"`, `ESTABELECIMENTO_CNES="5604613"`,
`ESTABELECIMENTO_NUCLEO="Núcleo Regional de Especialidade de Vitória"`, `ESTABELECIMENTO_UNIDADE="Unidade de Oftalmologia"`.

### 3.4 Fontes de valor dos campos (generalizar `atributo_paciente`, sem migração destrutiva)
Hoje `atributo_paciente` é um `getattr(paciente, …)`. Passa a aceitar **prefixo de fonte**; sem prefixo = paciente
(compatível com os templates existentes):

| Chave | Valor |
|---|---|
| `paciente.<attr>` ou `<attr>` | atributo do paciente; datas → `dd/mm/aaaa` |
| `paciente.nascimento_curto` | `dd/mm/aa` (o BPA-I usa `__/__/__`) |
| `paciente.telefone_contato` | celular ou telefone |
| `medico.nome` / `medico.crm` / `medico.cns` / `medico.cbo` / `medico.rqe` / `medico.assinatura` | do médico escolhido; `assinatura` = "Dr(a). NOME" + linha "CRM: …" |
| `estabelecimento.nome` / `.cnes` / `.nucleo` / `.unidade` | settings |
| `atendimento.data` | data do atendimento escolhido (dd/mm/aaaa) |
| `atendimento.mes_ano` | mm/aaaa da data do atendimento |
| `sistema.hoje` | data de hoje |

Formatação centralizada numa função `resolver_valor(chave, contexto)` com testes. Valor digitado no
formulário **sempre vence** o automático (o automático vira `value` inicial do input, editável).

### 3.5 Tela "Gerar documento"
- Novo select **Médico** (obrigatório quando o template usa `medico.*`): pré-seleciona o `Medico` ligado ao
  `request.user`; senão, o último usado pelo usuário (sessão); senão vazio.
- Novo campo **Data do atendimento** (date): default = agendamento do paciente hoje; senão o próximo; senão hoje.
- Ao escolher paciente/médico/data, os campos automáticos aparecem **pré-preenchidos e editáveis**
  (endpoint JSON `valores_automaticos?paciente=&medico=&data=&template=`).
- `Documento` guarda `medico` (FK nova, nullable) e `data_atendimento` (DateField nullable).

## 4. Tipos de campo novos/ajustados na engine

1. **`procedimentos`** (novo `tipo_campo`): UI = lista de checkboxes de `Procedimento` ativos, **agrupada por `grupo`**,
   com busca por código/nome (filtro client-side). Cada item mostra código, nome e instrumentos.
   Impressão: **um BPA-I por procedimento marcado** — a página base é repetida para cada procedimento, com
   `nome` e `código` nas posições do campo; os demais campos se repetem iguais em todas as páginas.
   QTD por procedimento: input numérico ao lado do item marcado (default 1, impresso como `01`).
2. **`checkbox` com opção composta** (receituário): cada opção pode ter várias posições de "X" e as posições
   podem se repetir (2 vias). Já suportado parcialmente: `opcoes[].posicao` vira **lista** de posições.
3. **`radio`/`select`** imprime o **texto** da opção (hoje imprimiria o id) — corrigir.
4. Campo em **várias posições** (`posicao` lista) — já existe; usado nas 2 vias do receituário.
5. Fonte/tamanho por posição; texto que não cabe na largura reduz a fonte até 7pt (sem estourar a caixa).

## 5. Layouts

### 5.1 BPA-I — "Solicitação de Procedimento (BPA-I)" — A4 retrato
Cabeçalho: logo SUS à esquerda. Quadros com borda, títulos em negrito, como no modelo:

**Dados Operacionais**
| Rótulo | Campo | Fonte |
|---|---|---|
| Mês/ano | texto | `atendimento.mes_ano` |
| Data do Atendimento | texto | `atendimento.data` |
| Nome do Estabelecimento / CNES | texto | `estabelecimento.nome` / `.cnes` |
| CNS do Profissional / CBO | texto | `medico.cns` / `medico.cbo` |
| Nome do Paciente | texto | `paciente.nome` |
| Sexo ( )M ( )F | radio M/F → "X" | `paciente.sexo` (editável) |
| Nº CNS do Usuário | texto | `paciente.cns` |
| Data Nascimento | texto | `paciente.nascimento_curto` |
| Raça/Cor | select: 01 Branca, 02 Preta, 03 Parda, 04 Amarela, 05 Indígena, 99 Sem informação | manual |
| Telefone | texto | `paciente.telefone_contato` |
| Nome da Mãe | texto | `paciente.nome_mae` se existir (ver §7), senão manual |
| Endereço / Município / CEP | texto | manual |

**Procedimento Solicitado**: Nome do procedimento + Cód. Procedimento (campo `procedimentos`), QTD, CID-10
(texto, manual, ex. `H00.1`), Car. Atend. (select: 01 Eletivo, 02 Urgência, 03 Acidente local de trabalho, 04 Acidente de
trajeto, 05 Outros acidentes de trânsito, 06 Outras lesões/envenenamentos; default 01), Médico solicitante
(`medico.nome`), CNS do Profissional (`medico.cns`), linha "Ass. e carimbo do Solicitante".

**Justificativa**: Hipótese Diagnóstica (texto) + CID-10 (texto; default = CID do procedimento solicitado se informado).

**Resumo do Exame Físico**: textarea grande, valor inicial "BAV: ".

**CAMPO RESERVADO PARA O AUTORIZADOR**: Nº Autorização, Data `__/__/____`, linha "Médico Autorizador" —
**impressos em branco** (não são campos).

### 5.2 Prescrição de Óculos — A4 retrato
Cabeçalho: `logo_governo_es.jpeg` (≈ 6 cm de largura). Linhas em negrito: `estabelecimento.nucleo`,
`estabelecimento.unidade`, "PRESCRIÇÃO DE ÓCULOS". `Nome:` (`paciente.nome`).
Tabelas **LONGE** e **PERTO**: colunas OLHO | ESFÉRICO | CILINDRO | EIXO, linhas Direito/Esquerdo → 12 campos de texto
curtos (centralizados na célula). `ADD: +` (texto). `Data do Atendimento:` (`atendimento.data`).
Rodapé: linha de assinatura, `Dr(a). medico.nome`, `CRM: medico.crm`, `medico.especialidade_exibicao`.

### 5.3 Receituário de Colírios — A4 **paisagem, 2 vias lado a lado** (cada via = metade da página)
Cada via: faixa `cabecalho_sus_es.png` + caixa "RECEITUÁRIO"; `UNIDADE DE SAÚDE: CRE – METROPOLITANO`
(`estabelecimento.nome`); `NOME:` (`paciente.nome`); "USO OCULAR:"; itens (texto fixo impresso no PDF base, como no modelo):

| # | Medicamento | Quantidade | Posologia (fixa) |
|---|---|---|---|
| 1 | Maleato de Timolol 0,5% | 1 frasco/mês | Pingar 01 (uma) gota de 12/12hs (07:00 e 19:00hs) |
| 2 | Travoprosta 0,004% | 1 frasco/mês | Pingar 01 (uma) gota às 20:00hs (todas as noites) |
| 3 | Bimatoprosta 0,03% | 1 frasco/mês | Pingar 01 (uma) gota às 20:00hs (todas as noites) |
| 4 | Latanoprosta 0,005% | 1 frasco/mês | Pingar 01 (uma) gota às 20:00hs (todas as noites) |
| 5 | Tartarato de Brimonidina 0,2% | 1 frasco/mês | Pingar 01 (uma) gota de 12/12hs (07:30 e 19:30hs) |
| 6 | Dorzolamida 2% | 1 frasco/mês | Pingar 01 (uma) gota de 12/12hs (07:45 e 19:45hs) |
| 7 | Brinzolamida 1% | 1 frasco/mês | Pingar 01 (uma) gota de 12/12hs (07:45 e 19:45hs) |

Cada item: `[ ]` do medicamento + `[ ] Olho Direito [ ] Olho Esquerdo`. No formulário, cada medicamento é uma linha
com 3 checkboxes (usar / OD / OE); marcar OD ou OE marca "usar" automaticamente. "X" impresso nas posições das
**duas vias**.
"USO ORAL:" item 8 — Acetazolamida comprimido 250mg (da LISTA DE COLÍRIOS), com campo de texto livre para
quantidade/posologia (não há posologia padrão no modelo).
Rodapé de cada via: `DATA:` (`atendimento.data`), linha de assinatura, `Dr(a). medico.nome`, `CRM: medico.crm`,
`medico.especialidade_exibicao`, "Ao voltar à consulta traga esta receita".

Remover/desativar o template antigo "Receituario Colirio - Timolol" só se não houver `Documento` emitido com ele.

## 6. Critérios de aceite
- [ ] `instalar_templates_oftalmo` roda 2x sem duplicar nada; 3 templates ativos com os campos acima.
- [ ] `importar_procedimentos_sigtap` carrega os 146 procedimentos; calázio `04.05.01.007-9` presente.
- [ ] Paciente importado do MV + médico + data → BPA-I com mês/ano, data, estabelecimento/CNES, CNS/CBO do médico, nome,
      CNS e nascimento do paciente preenchidos sem digitar.
- [ ] 3 procedimentos marcados → PDF com 3 páginas, uma por procedimento, demais dados iguais.
- [ ] Receituário: marcar Timolol OD+OE e Dorzolamida OE → "X" nas posições certas **nas duas vias**.
- [ ] Prescrição: 12 valores das tabelas centralizados nas células; assinatura com nome/CRM do médico.
- [ ] Valor editado no formulário vence o automático.
- [ ] Testes: `resolver_valor` (todas as chaves e formatações), engine (multi-página por procedimento, checkbox multi-posição,
      select imprime texto, ajuste de fonte), command idempotente, view com pré-preenchimento. Teste visual: PNG das 3
      páginas geradas com dados sintéticos anexado ao relatório (pymupdf só em dev).
- [ ] Nenhum dado real de médico/paciente em fixture, teste ou log.

## 7. Pendências de decisão (do usuário)
- **Completar dados de pacientes já importados** (sexo, nome da mãe, profissional do agendamento) a partir do MV, só
  preenchendo campos vazios. Enquanto não decidido: `nome_mae` não existe no model e o campo do BPA-I é manual.
