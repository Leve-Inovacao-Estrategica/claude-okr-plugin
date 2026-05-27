---
name: okr
description: Gerenciar tarefas no Leve OKR (plataforma interna da Leve Inovação Estratégica). Use quando o usuário pedir para listar/criar/atualizar/concluir tarefas, mencionar projetos por nome (Santa Maria Outlet, SOL Engrenagens, EW Incorporadora, Precifica Simples, Compras White Label, Gestou, POD Pratas925) ou seus apelidos curtos (SMO, SOL, EW, Precifica, Compras, Gestou, POD). TRIGGER quando o usuário disser coisas como "adicionar tarefa", "criar tarefa", "marcar como feito", "marcar como concluída", "listar tarefas", "tarefas pendentes do X", "o que falta no X", "status do projeto X". SKIP quando o pedido não envolver tarefas/projetos da Leve OKR.
---

# OKR — Leve OKR task management

Plataforma interna da Leve Inovação Estratégica para gerenciar OKRs e tarefas de projetos com clientes. Esta skill conversa com a Agent API do Leve OKR em `https://okr.leveinovacao.com.br` via o helper `claude-okr`.

## Pré-requisito: autenticação (UX crítica — leia com atenção)

Antes de qualquer chamada à API, garanta que o usuário está autenticado via PAT (Personal Access Token).

### Caso A — já autenticado (caminho comum)

Rode silenciosamente:
```bash
claude-okr ensure-login
```

Se sair com 0, segue direto pra próxima operação. Se sair com **exit 2** (mensagem `AUTH_REQUIRED`), vá pro caso B.

### Caso B — precisa logar (1ª vez na máquina, token expirou, etc.)

**Não chame `claude-okr login` direto** — esse comando faz tudo dentro do Bash tool, e a URL pra autorizar fica escondida atrás de "Ctrl+O / expandir". O usuário não consegue acionar o navegador sem clicar pra expandir o output.

**Em vez disso, siga este protocolo de 3 passos em sequência, mostrando a URL no chat:**

**Passo 1 — gerar o código** (rápido, retorna JSON em STDOUT):
```bash
claude-okr login-start
```
Saída esperada:
```json
{
  "user_code": "ABCD-1234",
  "verification_uri": "https://okr.leveinovacao.com.br/cli-auth?code=ABCD-1234",
  "expires_in_seconds": 600
}
```

**Passo 2 — MOSTRAR A URL NO CHAT (NÃO dentro do Bash block):**

Renderize uma mensagem clara e visível pro usuário, por exemplo:

> 🔑 **Você precisa autorizar o plugin uma vez.**
>
> Abra esta URL no navegador e clique em "Autorizar":
>
> https://okr.leveinovacao.com.br/cli-auth?code=ABCD-1234
>
> Código: **ABCD-1234** (válido por 10 min)
>
> Aguardando você autorizar...

A URL precisa aparecer **fora** de bloco de código de tool — em texto markdown no chat normal. O usuário tem que ver e clicar sem precisar expandir nada.

**Passo 3 — esperar a aprovação** (polling, bloqueia até resolver):
```bash
claude-okr login-wait
```
Quando o usuário clicar "Autorizar" no browser, esse comando termina com `✅ Autenticado como ...`. Daí prossiga com a operação original.

### Caso C — token salvo mas inválido (raro)

`claude-okr ensure-login` ou `claude-okr call` retorna `AUTH_REQUIRED: token inválido ou expirado`. Rode `claude-okr logout` e siga o caso B.

### Restrição importante

Só emails `@leveinovacao.com.br` podem autorizar. Outras pessoas conseguem instalar o plugin mas o `/cli-auth/approve` recusa.

**Nunca faça curl direto com Bearer:** o helper `claude-okr call` injeta o token automaticamente e ainda revalida. Use sempre ele.

## Projetos disponíveis

Slugs estáveis dos projetos (resolva por apelido quando o usuário falar nome livre):

| Slug | Cliente | Apelidos comuns |
|---|---|---|
| `smo-2026` | Santa Maria Outlet | SMO, santa maria, outlet |
| `sol-2026` | SOL Engrenagens | SOL, sol engrenagens |
| `ew-2026` | EW Incorporadora | EW, EW Incorporações |
| `precifica-2026` | Precifica Simples | Precifica |
| `compras-2026` | Sistema de Compras (White Label) | Compras, white label |
| `gestou-2026` | Gestou | Gestou |
| `podpratas-2026` | POD Pratas925 | POD, POD Pratas, pratas |

Em caso de ambiguidade, confirme com o usuário antes de prosseguir.

> O slug corresponde ao campo `agentSlug` no `Project` do banco — independente do `publicToken` (portal público), que pode continuar desligado. A Agent API resolve `?projectToken=...` em qualquer um dos dois campos.

## Usuários conhecidos (resolução de email)

Quando o usuário citar uma pessoa pelo primeiro nome, mapeie pra um email:

| Nome | Email |
|---|---|
| Rafael / Rafa | rafael@leveinovacao.com.br |
| Yuri | yuri@leveinovacao.com.br |
| João / João Pedro / JP | joao@leveinovacao.com.br *(confirmar exato)* |
| Guilherme / Gui | guilherme@leveinovacao.com.br *(confirmar exato)* |

Se o usuário não especificar responsável ao **criar** uma tarefa, assuma que é pra ele mesmo (o backend resolve pelo dono do PAT, então é automático — não precisa passar `responsibleEmail`).

## Endpoints disponíveis

```
GET   /api/agent/projects                                              → lista projetos
GET   /api/agent/tasks?projectToken=...&status=...&responsibleEmail=...&dueBefore=YYYY-MM-DD
GET   /api/agent/tasks/{id}                                             → detalhe
POST  /api/agent/tasks                                                  → criar em lote
PATCH /api/agent/tasks/{id}                                             → atualizar (status, dueDate, responsibleEmail, title, description)
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

Fluxo obrigatório:

1. **Monte o payload** com base no pedido do usuário
2. **Mostre preview** em formato legível:
   ```
   Vou criar essas tarefas em SMO:
     • "Revisar plano comercial" — responsável: Rafael — prazo: 2026-05-30
     • "Apresentação Q2" — responsável: Yuri — prazo: 2026-06-15
   
   Confirma? (s/n)
   ```
3. **Espere "s", "sim", "ok", "confirmo"** antes de executar
4. **Execute** apenas se confirmado:

```bash
claude-okr call POST /api/agent/tasks '{
  "projectToken": "smo-2026",
  "tasks": [
    {"title": "Revisar plano comercial", "dueDate": "2026-05-30", "origin": "claude-code-plugin"}
  ]
}'
```

Notas:
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

Campos suportados em PATCH: `status` (PENDING|IN_PROGRESS|COMPLETED), `dueDate` (YYYY-MM-DD ou null), `responsibleEmail` (resolve User; null disconnect), `responsibleName`, `title`, `description`. Mesma lógica de preview → confirma → executa.

### 📊 Status do projeto (leitura — direto)

Para "como está o SMO":
1. `claude-okr call GET '/api/agent/tasks?projectToken=smo-2026'` (todas)
2. Agrupar por status
3. Apresentar `X pendentes, Y em andamento, Z concluídas (de N total)`
4. Listar as 3-5 atrasadas (status ≠ COMPLETED && dueDate < hoje) se houver

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
