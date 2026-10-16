---
name: okr
description: Consulte e gerencie tarefas, metas, check-ins e progresso dos projetos da Leve OKR. Use para pedidos sobre a plataforma Leve OKR; não para planejamento genérico de projetos.
---

# OKR — Leve OKR task management

Plataforma interna da Leve Inovação Estratégica para gerenciar OKRs e tarefas de projetos com clientes. Esta skill conversa com a Agent API do Leve OKR em `https://okr.leveinovacao.com.br` via o helper `python "<SKILL_DIR>/scripts/okr.py"`.

## Execução nos dois clientes

A mesma skill funciona no Claude Code e no Codex. Requer Python 3.9+ e acesso de rede ao Leve OKR; não requer Bash, curl ou pacotes pip.

Nos exemplos, `<SKILL_DIR>` é o diretório que contém este `SKILL.md`. Substitua pelo caminho absoluto informado pelo cliente ao carregar a skill; nunca execute o placeholder literalmente. O helper está em `scripts/okr.py` dentro desse diretório, inclusive quando a skill é instalada isoladamente.

Use `python` no Windows e `python3` em Linux/macOS, conforme o interpretador disponível. Não assuma que `claude-okr` está no PATH. No login, passe o nome do cliente: `login-start "Codex"` ou `login-start "Claude Code"`.

Para evitar problemas com aspas no PowerShell, passe o JSON por arquivo UTF-8: `call POST /api/agent/tasks '@payload.json'`, ou use `-` para ler stdin. O arquivo deve conter só o payload, nunca credenciais.

No uso pelo assistente, desabilite a abertura automática do navegador antes de `login-start`: PowerShell `$env:OKR_NO_BROWSER = "1"`; Bash `export OKR_NO_BROWSER=1`. Mostre a URL retornada no chat antes de iniciar `login-wait` e acompanhe a espera usando a ferramenta de processos do cliente.

## ⚠️ AUTENTICAÇÃO — UX CRÍTICA, SIGA EXATO

Toda chamada à API precisa de PAT. Quando o PAT não existe, o assistente PRECISA mostrar a URL no chat IMEDIATAMENTE — sem o usuário ver, ele não consegue autorizar.

### Protocolo obrigatório (4 passos)

**Passo 1 — Tente operação.** Se `python "<SKILL_DIR>/scripts/okr.py" call ...` ou `python "<SKILL_DIR>/scripts/okr.py" ensure-login` retornar **exit 2** com `AUTH_REQUIRED`, siga pra Passo 2.

**Passo 2 — Rode `login-start` em PRIMEIRO PLANO** (NÃO em background — é instantâneo, <2s):
```bash
python "<SKILL_DIR>/scripts/okr.py" login-start
```
Saída:
```json
{
  "user_code": "ABCD-1234",
  "verification_uri": "https://okr.leveinovacao.com.br/cli-auth?code=ABCD-1234",
  "expires_in_seconds": 600,
  "browser_opened": false
}
```
Esse comando tenta abrir o navegador padrão. No uso pelo assistente, defina `OKR_NO_BROWSER=1` e mostre o link no chat.

**Passo 3 — IMEDIATAMENTE depois, MOSTRE A URL NO CHAT** (em markdown, fora de qualquer bloco de tool). Exemplo de mensagem ideal:

> 🔑 **Autorize o plugin uma vez:**
>
> Abra no navegador: https://okr.leveinovacao.com.br/cli-auth?code=ABCD-1234
>
> Código: `ABCD-1234` (válido 10 min). Aguardando autorização...

**Não pule este passo.** A URL precisa aparecer em uma mensagem do assistente, não apenas na saída de uma ferramenta.

**Passo 4 — Rode `login-wait` (pode ser em background ou foreground):**
```bash
python "<SKILL_DIR>/scripts/okr.py" login-wait
```
Bloqueia até o usuário clicar "Autorizar" no browser. Termina com `Autenticado como ...`. Daí retoma a operação original que tinha falhado.

### Casos de borda

- **Já autenticado** (caminho mais comum): `python "<SKILL_DIR>/scripts/okr.py" ensure-login` sai com 0. Pode pular pro próximo passo da operação direto.
- **Token salvo mas inválido**: erros começam com `AUTH_REQUIRED`. Siga o protocolo de 4 passos para refazer o login; um erro de rede ou HTTP 500 não exige apagar credenciais.
- **Negado / código expirado**: `login-wait` morre com mensagem clara. Mostre o erro pro usuário e ofereça refazer (`login-start` de novo).

### Restrição

Só emails `@leveinovacao.com.br` podem autorizar PAT. Outras pessoas conseguem instalar o plugin mas o `/cli-auth/approve` recusa.

**Nunca faça curl direto com Bearer:** o helper `python "<SKILL_DIR>/scripts/okr.py" call` injeta o token e revalida. Use sempre ele.

## Projetos (resolução dinâmica — NÃO hardcode)

A lista de projetos vive no banco e muda. **Sempre** resolva o projeto consultando a API, nunca uma tabela memorizada:

```bash
python "<SKILL_DIR>/scripts/okr.py" call GET /api/agent/projects
```

Cada item traz `name`, `agentSlug`, `color` e `_count` de tasks/goals. Faça o match entre o que o usuário falou (nome livre, apelido ou sigla) e o `name`/`agentSlug` retornado, e use o `agentSlug` como `projectToken` nas demais chamadas.

- Cacheie o resultado dentro da mesma conversa pra não repetir a chamada a cada operação.
- Em caso de ambiguidade (mais de um match plausível), liste os candidatos e **confirme com o usuário** antes de prosseguir.

> `agentSlug` é o campo do `Project` no banco — independente do `publicToken` (portal público), que pode continuar desligado. A Agent API resolve `?projectToken=...` tanto por `agentSlug` quanto por `publicToken`.

## Usuários / responsáveis (resolução dinâmica — NÃO hardcode)

Pessoas e emails também vêm do banco. Pra mapear um primeiro nome ("Rafael", "Yuri", "João", "Gui") num email/responsável, consulte:

```bash
python "<SKILL_DIR>/scripts/okr.py" call GET /api/agent/users
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
      &completedAfter=YYYY-MM-DD&completedBefore=YYYY-MM-DD             → janela de CONCLUSÃO (lista da daily)
GET   /api/agent/tasks/{id}                                             → detalhe (inclui o array `actions`)
POST  /api/agent/tasks                                                  → criar em lote (body: {projectToken, tasks: [...]}; cada task exige goalId OU goalTitle)
PATCH /api/agent/tasks/{id}                                             → atualizar (status, dueDate, responsibleEmail, title, description, goalId/goalTitle p/ mover de meta)
GET   /api/agent/tasks/{id}/actions                                     → histórico de ações da tarefa
POST  /api/agent/tasks/{id}/actions                                     → registrar ação executada (body: {"content": "..."})
PATCH /api/agent/tasks/{id}/actions/{actionId}                          → corrigir o conteúdo de uma ação (carimba "editado")
DELETE /api/agent/tasks/{id}/actions/{actionId}                         → remover ação registrada por engano
POST  /api/agent/uploads/image                                          → subir print (use `python "<SKILL_DIR>/scripts/okr.py" upload <arquivo>`)
```

`{id}` de tarefa aceita o **cuid** ou o **code curto** (`#123` → `/api/agent/tasks/123`) — o code é
o que aparece no painel, prefira ele ao falar com o usuário.

Sempre via `python "<SKILL_DIR>/scripts/okr.py" call <METHOD> <PATH> [<JSON_BODY>]`.

> **Erros vêm no corpo.** `python "<SKILL_DIR>/scripts/okr.py" call` imprime a resposta mesmo em 4xx/5xx e sai 1 —
> leia o campo `error` (ex.: `content is required`, ou a lista de metas disponíveis num 400
> de criação) em vez de tentar adivinhar o schema.

## Operações

### 📖 Listar tarefas (leitura — execute direto, sem confirmar)

Para "tarefas pendentes do projeto X" (resolva o slug antes, como na seção acima):

```bash
python "<SKILL_DIR>/scripts/okr.py" call GET '/api/agent/tasks?projectToken=<slug-do-projeto>&status=PENDING'
```

Apresente como tabela: `[status] título — responsável — prazo`. Se vier vazio, diga "nenhuma tarefa pendente" nomeando o projeto que o usuário citou.

Para "minhas tarefas pendentes em todos os projetos": liste projetos primeiro, depois itere com `responsibleEmail=<email-do-user>`. Para descobrir o email atual, confirme com o usuário. As credenciais contêm apenas o token; não leia nem exiba esse arquivo no chat. `whoami` verifica o token e conta projetos, mas não retorna identidade.

### ➕ Criar tarefa (escrita — **SEMPRE confirme antes**)

> ⚠️ **Toda tarefa precisa de uma meta.** O backend é estrito: `POST` sem `goalId`/`goalTitle`
> resolvível devolve `400` (com a lista de metas disponíveis no corpo). Resolva a meta ANTES.

Fluxo obrigatório:

1. **Descubra a meta.** Liste as metas do projeto:
   ```bash
   python "<SKILL_DIR>/scripts/okr.py" call GET '/api/agent/goals?projectToken=<slug-do-projeto>'
   ```
   - Se o usuário **indicou** a meta (por nome), case com a lista e use o `id` (campo `goalId`).
   - Se **não indicou**, **pergunte qual meta** antes de prosseguir — não invente nem escolha sozinho.
2. **Monte o payload** com `goalId` (preferencial) ou `goalTitle` (match exato do título no projeto) em cada task.
3. **Mostre preview** em formato legível, incluindo a meta:
   ```
   Vou criar essas tarefas em <Projeto> › meta "Aumentar faturamento Q2":
     • "Revisar plano comercial" — responsável: Rafael — prazo: 2026-05-30
     • "Apresentação Q2" — responsável: Yuri — prazo: 2026-06-15

   Confirma? (s/n)
   ```
4. **Espere "s", "sim", "ok", "confirmo"** antes de executar
5. **Execute** apenas se confirmado:

```bash
python "<SKILL_DIR>/scripts/okr.py" call POST /api/agent/tasks '{
  "projectToken": "<slug-do-projeto>",
  "tasks": [
    {"title": "Revisar plano comercial", "goalId": "cmxxxx...", "dueDate": "2026-05-30", "origin": "claude-code-plugin"}
  ]
}'
```

Notas:
- **`goalId`/`goalTitle` é obrigatório** em cada task — sem isso o backend rejeita (400). Cada task pode ir pra uma meta diferente.
- `goalId` é o caminho seguro; `goalTitle` é conveniência (match exato case-insensitive; se ambíguo, o backend pede `goalId`).
- Mantenha `"origin": "claude-code-plugin"` nos dois clientes por compatibilidade com o backend atual.
- Quando não há responsibleEmail explícito, o backend atribui automaticamente ao dono do PAT — não precisa passar
- Para atribuir a outra pessoa, inclua `"responsibleEmail": "fulano@leveinovacao.com.br"` na task

### ✅ Marcar como concluída (escrita — **SEMPRE confirme antes**)

Se o usuário disser "marca a X como feito" sem ID, primeiro **liste com filtros** pra encontrar o ID. Não chute.

Fluxo:
1. Buscar: `python "<SKILL_DIR>/scripts/okr.py" call GET '/api/agent/tasks?projectToken=...&status=PENDING'`
2. Match por título mais próximo (se múltiplos candidatos, peça pro usuário escolher pelo número)
3. Preview:
   ```
   Achei: "5.10 — Consolidação dos Charts" (id cmnxnj70m000hs1aq8xd94h8q) em <Projeto>
   Status atual: IN_PROGRESS → vai virar COMPLETED.
   Confirma? (s/n)
   ```
4. Espere confirmação
5. Execute:
```bash
python "<SKILL_DIR>/scripts/okr.py" call PATCH /api/agent/tasks/{id} '{"status": "COMPLETED"}'
```

### 🔄 Atualizar tarefa (escrita — **SEMPRE confirme antes**)

Campos suportados em PATCH: `status` (PENDING|IN_PROGRESS|COMPLETED), `dueDate` (YYYY-MM-DD ou null), `responsibleEmail` (resolve User; null disconnect), `responsibleName`, `title`, `description`, `goalId`/`goalTitle` (move a tarefa pra outra meta — a meta-alvo precisa ser do mesmo projeto). Mesma lógica de preview → confirma → executa.

### 🧾 Ações de tarefa — o que foi feito (escrita de histórico)

A **descrição** guarda o enunciado da tarefa; a **ação** guarda o que foi executado. Ao fechar
uma sessão de trabalho que tocou uma tarefa, registre uma ação resumindo o que foi feito — não
infle a descrição.

```bash
python "<SKILL_DIR>/scripts/okr.py" call POST /api/agent/tasks/625/actions '{"content": "Ajustado o parser de datas; deploy na revision 00013."}'
```

- `content` é obrigatório (rich text: HTML simples ou texto puro). Sem ele → `400 content is required`.
- O autor é o dono do PAT — não passe `authorName` a menos que esteja registrando por outra pessoa.
- Diferente de criar tarefa, isto **não** exige confirmação prévia: é registro do que já aconteceu.

**Anexar print (evidência visual da daily):** suba a imagem e cole o `html` devolvido no `content`.

```bash
python "<SKILL_DIR>/scripts/okr.py" upload /tmp/print.png
# → {"url":"/api/task-images/...","absoluteUrl":"https://...","html":"<img src=\"/api/task-images/...\" style=\"width: 60%\" />"}

python "<SKILL_DIR>/scripts/okr.py" call POST /api/agent/tasks/625/actions '{"content": "Painel novo no ar:<br /><img src=\"/api/task-images/<org>/<user>/177....png\" style=\"width: 60%\" />"}'
```

**Corrigir ou apagar uma ação** (typo, ação registrada na tarefa errada):

```bash
python "<SKILL_DIR>/scripts/okr.py" call PATCH  /api/agent/tasks/625/actions/<actionId> '{"content": "texto corrigido"}'
python "<SKILL_DIR>/scripts/okr.py" call DELETE /api/agent/tasks/625/actions/<actionId>
```

O PATCH preserva autor e data original e marca a ação como "editado" no painel. Pegue o
`actionId` em `GET /api/agent/tasks/{id}/actions`. Apagar é destrutivo — **confirme antes**.

### 📅 Lista da daily — o que foi entregue (leitura — direto)

Para "o que foi concluído hoje", use a janela de **conclusão**, não `updatedAt` (que se move a
cada edição):

```bash
python "<SKILL_DIR>/scripts/okr.py" call GET "/api/agent/tasks?projectToken=<slug-do-projeto>&completedAfter=<YYYY-MM-DD>"
```

`completedAfter`/`completedBefore` aceitam `YYYY-MM-DD` e cobrem o dia inteiro em horário de
Brasília. Combine os dois para a semana. Cada tarefa traz `_count.actions` — para contar o que
foi registrado, e `GET /api/agent/tasks/{id}` traz o histórico completo quando o usuário pedir
detalhe.

> Tarefas concluídas antes de 2026-09-08 têm `completedAt` estimado a partir da última edição
> (backfill). Para datas antigas, trate como aproximação.

### 📊 Status do projeto (leitura — direto)

Para "como está o projeto X":
1. `python "<SKILL_DIR>/scripts/okr.py" call GET '/api/agent/tasks?projectToken=<slug-do-projeto>'` (todas)
2. Agrupar por status
3. Apresentar `X pendentes, Y em andamento, Z concluídas (de N total)`
4. Listar as 3-5 atrasadas (status ≠ COMPLETED && dueDate < hoje) se houver

### 🎯 Metas / OKRs (leitura — direto)

Para perguntas sobre **objetivos/metas/OKR** (não tarefas): "como estão as metas do projeto X?", "qual o progresso do faturamento?", "tem alguma meta em risco?".

```bash
python "<SKILL_DIR>/scripts/okr.py" call GET '/api/agent/goals?projectToken=<slug-do-projeto>'
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
python "<SKILL_DIR>/scripts/okr.py" call POST /api/agent/goals/cml9...apdt/checkin '{"notes": "via plugin"}'
```
Sem confirmação prévia — não altera nenhum valor, só anexa a nota (o `progressPct` do momento é anexado automaticamente como snapshot).

**Meta `MANUAL`** — para "registra que o faturamento do projeto X chegou em R$ 3.500" / "atualiza a meta X pra 60 clientes". **`value` é obrigatório e é o valor ABSOLUTO atual da meta, não um incremento** — o backend faz `currentValue = value`.
- Se o usuário der um valor absoluto ("chegou em 3500"), use-o direto.
- Se falar em **incremento** ("subiu 500", "fechamos mais 2 clientes"), **primeiro leia a meta** via `/api/agent/goals` pra pegar o `currentValue` atual, some, e use o total. Mostre a conta no preview.

Fluxo (metas `MANUAL`, **sempre confirme antes** — é diferente do fluxo `AUTO`):
1. Resolva a meta e confirme que `progressMode` é `MANUAL`.
2. Preview com a conta explícita:
   ```
   Check-in na meta "Faturamento" (<Projeto>):
     currentValue 2600 → 3500 R$  (= 70% de 5000)
   Confirma? (s/n)
   ```
3. Espere confirmação.
4. Execute:
```bash
python "<SKILL_DIR>/scripts/okr.py" call POST /api/agent/goals/cml9...apdt/checkin '{"value": 3500, "notes": "via plugin"}'
```

Campos comuns: `notes` (opcional em `AUTO`, mas é o motivo de existir do check-in ali — peça se o usuário não deu contexto; opcional em `MANUAL`), `weekNumber` (opcional — auto-calculado pela semana atual se omitido).

> O check-in **não** muda o `status` da meta (ON_TRACK/AT_RISK/…) em nenhum dos dois modos. Se o usuário quiser mudar o status, isso é outra operação (não suportada por agora — avise).

## Regras de qualidade

- **Datas**: aceite linguagem natural ("amanhã", "sexta", "em 3 dias") e converta pra `YYYY-MM-DD`. Use a data atual em America/Sao_Paulo e passe datas literais; não dependa de comandos de shell Unix.
- **Match de tarefas por título**: priorize match exato; múltiplos candidatos → usuário escolhe pelo número da lista. **Nunca** atualize várias tarefas com um único pedido sem confirmação explícita.
- **Erros do backend**: se receber 400/404/500, mostre o `error` do JSON e pare. Não tente recuperar sozinho.
- **Limite de saída**: ao listar mais de 15 tarefas, mostre só as 10 mais relevantes (pendentes/em-andamento, ordenadas por prazo) e diga "+ N concluídas (peça pra ver tudo se quiser)".
- **Origin**: ao criar via skill, sempre marque `"origin": "claude-code-plugin"`. Esse é o valor legado compatível com a API. Não invente um novo origin sem confirmar suporte no backend.

## O que NÃO fazer

- Criação/edição de tarefas, edição/exclusão de ações e check-ins MANUAL exigem preview e confirmação; registros de ações e notas AUTO seguem as exceções descritas acima.
- Não chutar IDs de tarefa — sempre buscar primeiro
- Não usar `responsibleName` (string solta) quando puder usar `responsibleEmail` (vincula User real)
- Não silenciar erros — sempre mostrar o que o backend devolveu
- Não fazer `curl` direto com Bearer — use sempre `python "<SKILL_DIR>/scripts/okr.py" call` (injeta e valida o PAT; não faz refresh nem repete escritas automaticamente)

## Diagnóstico rápido

- `python "<SKILL_DIR>/scripts/okr.py" whoami` — confirma autenticação
- Erro `HTTP 400 ...` — o JSON impresso logo acima traz o campo `error` com o motivo exato
- Para refazer auth, use `login-start` e `login-wait`, mostrando o link no chat entre eles. `logout` remove as credenciais dos dois clientes.
- Para ambiente de desenvolvimento, configure `OKR_BASE_URL`: PowerShell `$env:OKR_BASE_URL = "http://localhost:3000"`; Bash `export OKR_BASE_URL=http://localhost:3000`.
