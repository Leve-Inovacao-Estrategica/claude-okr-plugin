---
name: okr
description: Gerenciar tarefas e metas/OKRs no Leve OKR (plataforma interna da Leve Inovação Estratégica). Use quando o usuário pedir para listar/criar/atualizar/concluir tarefas, consultar metas/objetivos/OKRs e seu progresso, ou mencionar projetos da Leve por nome ou apelido (ex.: Santa Maria Outlet/SMO, SOL Engrenagens/SOL, EW, Precifica, Compras White Label, Gestou — entre outros; a lista real vem da API, não é fixa). TRIGGER quando o usuário disser coisas como "adicionar tarefa", "criar tarefa", "marcar como feito", "marcar como concluída", "listar tarefas", "tarefas pendentes do X", "o que falta no X", "status do projeto X", "como estão as metas do X", "progresso do objetivo Y", "tem meta em risco". SKIP quando o pedido não envolver tarefas/metas/projetos da Leve OKR.
---

# OKR — Leve OKR task management

Plataforma interna da Leve Inovação Estratégica para gerenciar OKRs e tarefas de projetos com clientes. Esta skill conversa com a Agent API do Leve OKR em `https://okr.leveinovacao.com.br` via o helper `claude-okr`.

## ⚠️ AUTENTICAÇÃO — UX CRÍTICA, SIGA EXATO

Toda chamada à API precisa de PAT. Quando o PAT não existe, você (Claude) PRECISA mostrar a URL no chat IMEDIATAMENTE — sem o usuário ver, ele não consegue autorizar.

### Protocolo obrigatório (4 passos)

**Passo 1 — Tente operação.** Se `claude-okr call ...` ou `claude-okr ensure-login` retornar **exit 2** com `AUTH_REQUIRED`, siga pra Passo 2.

**Passo 2 — Rode `login-start` em PRIMEIRO PLANO** (NÃO em background — é instantâneo, <2s):
```bash
claude-okr login-start
```
Saída:
```json
{
  "user_code": "ABCD-1234",
  "verification_uri": "https://okr.leveinovacao.com.br/cli-auth?code=ABCD-1234",
  "expires_in_seconds": 600,
  "browser_opened": true
}
```
Esse comando **já tenta abrir o navegador** do usuário com `xdg-open`/`open`. Não rode em background.

**Passo 3 — IMEDIATAMENTE depois, MOSTRE A URL NO CHAT** (em markdown, fora de qualquer bloco de tool). Exemplo de mensagem ideal:

> 🔑 **Autorize o plugin uma vez:**
>
> Abri o navegador. Se não abriu sozinho, abra: https://okr.leveinovacao.com.br/cli-auth?code=ABCD-1234
>
> Código: `ABCD-1234` (válido 10 min). Aguardando autorização...

⚠️ **NÃO pule este passo. NÃO esconda a URL no Bash block.** Se a URL ficar só dentro do output do Bash, o usuário precisa clicar em "Ctrl+O / expandir" pra ver — UX horrível.

**Passo 4 — Rode `login-wait` (pode ser em background ou foreground):**
```bash
claude-okr login-wait
```
Bloqueia até o usuário clicar "Autorizar" no browser. Termina com `✅ Autenticado como ...`. Daí retoma a operação original que tinha falhado.

### Casos de borda

- **Já autenticado** (caminho mais comum): `claude-okr ensure-login` sai com 0 silenciosamente. Pode pular pro próximo passo da operação direto.
- **Token salvo mas inválido**: erros começam com `AUTH_REQUIRED: token salvo está inválido`. Rode `claude-okr logout` e siga o protocolo de 4 passos.
- **Negado / código expirado**: `login-wait` morre com mensagem clara. Mostre o erro pro usuário e ofereça refazer (`login-start` de novo).

### Restrição

Só emails `@leveinovacao.com.br` podem autorizar PAT. Outras pessoas conseguem instalar o plugin mas o `/cli-auth/approve` recusa.

**Nunca faça curl direto com Bearer:** o helper `claude-okr call` injeta o token e revalida. Use sempre ele.

## Projetos (resolução dinâmica — NÃO hardcode)

A lista de projetos vive no banco e muda. **Sempre** resolva o projeto consultando a API, nunca uma tabela memorizada:

```bash
claude-okr call GET /api/agent/projects
```

Cada item traz `name`, `agentSlug`, `color` e `_count` de tasks/goals. Faça o match entre o que o usuário falou (nome livre ou apelido, ex: "SMO", "outlet", "santa maria") e o `name`/`agentSlug` retornado, e use o `agentSlug` como `projectToken` nas demais chamadas.

- Cacheie o resultado dentro da mesma conversa pra não repetir a chamada a cada operação.
- Em caso de ambiguidade (mais de um match plausível), liste os candidatos e **confirme com o usuário** antes de prosseguir.

> `agentSlug` é o campo do `Project` no banco — independente do `publicToken` (portal público), que pode continuar desligado. A Agent API resolve `?projectToken=...` tanto por `agentSlug` quanto por `publicToken`.

## Usuários / responsáveis (resolução dinâmica — NÃO hardcode)

Pessoas e emails também vêm do banco. Pra mapear um primeiro nome ("Rafael", "Yuri", "João", "Gui") num email/responsável, consulte:

```bash
claude-okr call GET /api/agent/users
```

Retorna `{ id, name, email, role }` dos usuários ativos. Faça o match por nome e use o `email` como `responsibleEmail`. Se houver mais de um match plausível, confirme com o usuário.

- Cacheie na mesma conversa.
- Se o usuário **não** especificar responsável ao criar uma tarefa, não precisa resolver nada: o backend atribui automaticamente ao dono do PAT. Só consulte `/api/agent/users` quando ele citar **outra** pessoa.

## Endpoints disponíveis

```
GET   /api/agent/projects                                              → lista projetos (fonte de verdade dos slugs)
GET   /api/agent/users?status=ACTIVE                                   → lista usuários (resolução nome→email)
GET   /api/agent/goals?projectToken=...                                → metas/OKRs do projeto (progresso + contagem de tarefas)
POST  /api/agent/goals/{id}/checkin                                    → check-in (AUTO: nota qualitativa; MANUAL: value absoluto → currentValue)
GET   /api/agent/tasks?projectToken=...&status=...&responsibleEmail=...&dueBefore=YYYY-MM-DD
GET   /api/agent/tasks/{id}                                             → detalhe
POST  /api/agent/tasks                                                  → criar em lote (cada task exige goalId OU goalTitle)
PATCH /api/agent/tasks/{id}                                             → atualizar (status, dueDate, responsibleEmail, title, description, goalId/goalTitle p/ mover de meta)
```

Sempre via `claude-okr call <METHOD> <PATH> [<JSON_BODY>]`.

## Operações

### 📖 Listar tarefas (leitura — execute direto, sem confirmar)

Para "tarefas pendentes do SMO":

```bash
claude-okr call GET '/api/agent/tasks?projectToken=smo-2026&status=PENDING'
```

Apresente como tabela: `[status] título — responsável — prazo`. Se vier vazio, diga "nenhuma tarefa pendente em SMO".

Para "minhas tarefas pendentes em todos os projetos": liste projetos primeiro, depois itere com `responsibleEmail=<email-do-user>`. Para descobrir o email atual, leia `~/.config/leve-okr/credentials` ou confirme com o usuário.

### ➕ Criar tarefa (escrita — **SEMPRE confirme antes**)

> ⚠️ **Toda tarefa precisa de uma meta.** O backend é estrito: `POST` sem `goalId`/`goalTitle`
> resolvível devolve `400` (com a lista de metas disponíveis no corpo). Resolva a meta ANTES.

Fluxo obrigatório:

1. **Descubra a meta.** Liste as metas do projeto:
   ```bash
   claude-okr call GET '/api/agent/goals?projectToken=smo-2026'
   ```
   - Se o usuário **indicou** a meta (por nome), case com a lista e use o `id` (campo `goalId`).
   - Se **não indicou**, **pergunte qual meta** antes de prosseguir — não invente nem escolha sozinho.
2. **Monte o payload** com `goalId` (preferencial) ou `goalTitle` (match exato do título no projeto) em cada task.
3. **Mostre preview** em formato legível, incluindo a meta:
   ```
   Vou criar essas tarefas em SMO › meta "Aumentar faturamento Q2":
     • "Revisar plano comercial" — responsável: Rafael — prazo: 2026-05-30
     • "Apresentação Q2" — responsável: Yuri — prazo: 2026-06-15

   Confirma? (s/n)
   ```
4. **Espere "s", "sim", "ok", "confirmo"** antes de executar
5. **Execute** apenas se confirmado:

```bash
claude-okr call POST /api/agent/tasks '{
  "projectToken": "smo-2026",
  "tasks": [
    {"title": "Revisar plano comercial", "goalId": "cmxxxx...", "dueDate": "2026-05-30", "origin": "claude-code-plugin"}
  ]
}'
```

Notas:
- **`goalId`/`goalTitle` é obrigatório** em cada task — sem isso o backend rejeita (400). Cada task pode ir pra uma meta diferente.
- `goalId` é o caminho seguro; `goalTitle` é conveniência (match exato case-insensitive; se ambíguo, o backend pede `goalId`).
- Sempre marque `"origin": "claude-code-plugin"` (diferencia tarefas criadas via plugin de outras fontes)
- Quando não há responsibleEmail explícito, o backend atribui automaticamente ao dono do PAT — não precisa passar
- Para atribuir a outra pessoa, inclua `"responsibleEmail": "fulano@leveinovacao.com.br"` na task

### ✅ Marcar como concluída (escrita — **SEMPRE confirme antes**)

Se o usuário disser "marca a X como feito" sem ID, primeiro **liste com filtros** pra encontrar o ID. Não chute.

Fluxo:
1. Buscar: `claude-okr call GET '/api/agent/tasks?projectToken=...&status=PENDING'`
2. Match por título mais próximo (se múltiplos candidatos, peça pro usuário escolher pelo número)
3. Preview:
   ```
   Achei: "5.10 — Consolidação dos Charts" (id cmnxnj70m000hs1aq8xd94h8q) em SMO
   Status atual: IN_PROGRESS → vai virar COMPLETED.
   Confirma? (s/n)
   ```
4. Espere confirmação
5. Execute:
```bash
claude-okr call PATCH /api/agent/tasks/{id} '{"status": "COMPLETED"}'
```

### 🔄 Atualizar tarefa (escrita — **SEMPRE confirme antes**)

Campos suportados em PATCH: `status` (PENDING|IN_PROGRESS|COMPLETED), `dueDate` (YYYY-MM-DD ou null), `responsibleEmail` (resolve User; null disconnect), `responsibleName`, `title`, `description`, `goalId`/`goalTitle` (move a tarefa pra outra meta — a meta-alvo precisa ser do mesmo projeto). Mesma lógica de preview → confirma → executa.

### 📊 Status do projeto (leitura — direto)

Para "como está o SMO":
1. `claude-okr call GET '/api/agent/tasks?projectToken=smo-2026'` (todas)
2. Agrupar por status
3. Apresentar `X pendentes, Y em andamento, Z concluídas (de N total)`
4. Listar as 3-5 atrasadas (status ≠ COMPLETED && dueDate < hoje) se houver

### 🎯 Metas / OKRs (leitura — direto)

Para perguntas sobre **objetivos/metas/OKR** (não tarefas): "como estão as metas do Gestou?", "qual o progresso do faturamento?", "tem alguma meta em risco?".

```bash
claude-okr call GET '/api/agent/goals?projectToken=gestou-2026'
```

Cada meta retorna:
- `title`, `targetValue`/`currentValue`/`unit`, `progressPct`, e **`progressMode`: `AUTO` ou `MANUAL`** — decide como a completude é obtida e como o check-in funciona nessa meta específica:
  - **`AUTO`** (metas de execução, `unit` = `"tarefas"`): `currentValue`/`targetValue` são tarefas concluídas/total, recalculados a cada mutação de tarefa. `progressPct` é `null` só quando a meta ainda não tem nenhuma tarefa.
  - **`MANUAL`** (métricas de negócio: R$, clientes, leads, projetos, %): `currentValue`/`targetValue`/`unit` são o valor de negócio informado manualmente via check-in — igual sempre foi.
- `status`: `ON_TRACK` | `AT_RISK` | `BEHIND` | `COMPLETED` — em metas `AUTO`, `COMPLETED` também é automático (100% das tarefas); em `MANUAL` é sempre manual. Os demais status continuam manuais em ambos os modos.
- `dueDate`, `responsible`
- `taskCounts`: `{ pending, in_progress, completed, total }` das tarefas vinculadas (é a fonte do `progressPct` só em metas `AUTO`)

Como apresentar:
- Uma linha por meta: `título — currentValue/targetValue unit (progressPct%) — status — responsável`.
- **Destaque** as metas `AT_RISK`/`BEHIND` (ex: ⚠️) — é o que mais interessa.
- Se `progressPct` for `null`, mostre só `currentValue` (meta `MANUAL` sem alvo numérico, ou `AUTO` sem tarefas ainda) sem inventar porcentagem.

> Distinga **meta** de **tarefa**: meta é o objetivo macro (Goal); tarefa é o item de trabalho. "Como está a meta X" → `/api/agent/goals`. "O que falta fazer no projeto" → `/api/agent/tasks`.

### 📈 Check-in de meta (escrita — comportamento depende de `progressMode`)

**Sempre confira `progressMode` da meta primeiro** (via `/api/agent/goals`) antes de montar o check-in — o body é diferente em cada modo:

**Meta `AUTO`** — completude vem das tarefas; check-in é só uma nota qualitativa da semana, sem `value`. Use para "registra um check-in na meta X: fechamos a integração, falta só o teste final".
```bash
claude-okr call POST /api/agent/goals/cml9...apdt/checkin '{"notes": "via plugin"}'
```
Sem confirmação prévia — não altera nenhum valor, só anexa a nota (o `progressPct` do momento é anexado automaticamente como snapshot).

**Meta `MANUAL`** — para "registra que o faturamento do Gestou chegou em R$ 3.500" / "atualiza a meta X pra 60 clientes". **`value` é obrigatório e é o valor ABSOLUTO atual da meta, não um incremento** — o backend faz `currentValue = value`.
- Se o usuário der um valor absoluto ("chegou em 3500"), use-o direto.
- Se falar em **incremento** ("subiu 500", "fechamos mais 2 clientes"), **primeiro leia a meta** via `/api/agent/goals` pra pegar o `currentValue` atual, some, e use o total. Mostre a conta no preview.

Fluxo (metas `MANUAL`, **sempre confirme antes** — é diferente do fluxo `AUTO`):
1. Resolva a meta e confirme que `progressMode` é `MANUAL`.
2. Preview com a conta explícita:
   ```
   Check-in na meta "Faturamento" (Gestou):
     currentValue 2600 → 3500 R$  (= 70% de 5000)
   Confirma? (s/n)
   ```
3. Espere confirmação.
4. Execute:
```bash
claude-okr call POST /api/agent/goals/cml9...apdt/checkin '{"value": 3500, "notes": "via plugin"}'
```

Campos comuns: `notes` (opcional em `AUTO`, mas é o motivo de existir do check-in ali — peça se o usuário não deu contexto; opcional em `MANUAL`), `weekNumber` (opcional — auto-calculado pela semana atual se omitido).

> O check-in **não** muda o `status` da meta (ON_TRACK/AT_RISK/…) em nenhum dos dois modos. Se o usuário quiser mudar o status, isso é outra operação (não suportada por agora — avise).

## Regras de qualidade

- **Datas**: aceite linguagem natural ("amanhã", "sexta", "em 3 dias") e converta pra `YYYY-MM-DD`. Hoje é `date +%Y-%m-%d`.
- **Match de tarefas por título**: priorize match exato; múltiplos candidatos → usuário escolhe pelo número da lista. **Nunca** atualize várias tarefas com um único pedido sem confirmação explícita.
- **Erros do backend**: se receber 400/404/500, mostre o `error` do JSON e pare. Não tente recuperar sozinho.
- **Limite de saída**: ao listar mais de 15 tarefas, mostre só as 10 mais relevantes (pendentes/em-andamento, ordenadas por prazo) e diga "+ N concluídas (peça pra ver tudo se quiser)".
- **Origin**: ao criar via skill, sempre marque `"origin": "claude-code-plugin"`. Isso ajuda na auditoria.

## O que NÃO fazer

- Não fazer escritas (POST/PATCH) sem confirmação humana explícita
- Não chutar IDs de tarefa — sempre buscar primeiro
- Não usar `responsibleName` (string solta) quando puder usar `responsibleEmail` (vincula User real)
- Não silenciar erros — sempre mostrar o que o backend devolveu
- Não fazer `curl` direto com Bearer — use sempre `claude-okr call` (cuida do PAT, refresh, retry)

## Diagnóstico rápido

- `claude-okr whoami` — confirma autenticação
- `claude-okr logout && claude-okr login` — refaz auth se token bugou
- `OKR_BASE_URL=http://localhost:3000 claude-okr ...` — força ambiente diferente (dev local)
