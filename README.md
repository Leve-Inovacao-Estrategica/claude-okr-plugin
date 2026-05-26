# claude-okr-plugin

Plugin do Claude Code para gerenciar tarefas no [Leve OKR](https://okr.leveinovacao.com.br) via linguagem natural.

Autenticação por OAuth com a sua conta Google da Leve — uma vez por máquina, depois é só falar com o Claude Code.

## Instalação

Em qualquer sessão do Claude Code:

```
/plugin marketplace add Leve-Inovacao-Estrategica/claude-okr-plugin
/plugin install okr@leve
```

Na primeira chamada o plugin abre o navegador pra você autorizar via Google. Depois disso é só usar.

## Uso

Fale naturalmente com o Claude Code. Exemplos:

| Você diz | O plugin faz |
|---|---|
| *"quais tarefas pendentes do SMO?"* | Lista direto |
| *"como está o Gestou?"* | Resumo por status + atrasadas |
| *"minhas tarefas pendentes em todos os projetos"* | Itera os projetos |
| *"adiciona tarefa no SMO: revisar plano até sexta"* | Mostra preview → você confirma → cria |
| *"marca a 5.10 do SMO como concluída"* | Acha por título → confirma → marca |

Escritas (criar/atualizar/marcar) **sempre** pedem confirmação explícita antes de tocar a API.

## Comandos manuais

O plugin instala o helper `claude-okr` no PATH:

```bash
claude-okr login         # autentica via OAuth no navegador
claude-okr whoami        # mostra se está autenticado
claude-okr logout        # remove credenciais locais
claude-okr ensure-login  # garante que existe sessão válida
claude-okr call GET /api/agent/projects
```

## Credenciais

Token salvo em `~/.config/leve-okr/credentials` (chmod 600). Não é commitado em lugar nenhum.

Pra revogar do lado servidor: peça pro administrador deletar a linha correspondente em `ApiToken` no banco do Leve OKR.

## Projetos & apelidos suportados

| Slug | Cliente | Apelidos |
|---|---|---|
| `smo-2026` | Santa Maria Outlet | SMO, santa maria, outlet |
| `sol-2026` | SOL Engrenagens | SOL |
| `ew-2026` | EW Incorporadora | EW |
| `precifica-2026` | Precifica Simples | Precifica |
| `compras-2026` | Sistema de Compras (White Label) | Compras |
| `gestou-2026` | Gestou | Gestou |
| `podpratas-2026` | POD Pratas925 | POD, pratas |

> O slug é o `agentSlug` do projeto no banco — independente do `publicToken` (portal público), que pode permanecer NULL. Plugin **não** ativa portais públicos.

## Restrição

Só autoriza emails `@leveinovacao.com.br`. Outras pessoas podem instalar o plugin mas não conseguem operar.

## Variável de ambiente

`OKR_BASE_URL` — default `https://okr.leveinovacao.com.br`. Sobrescreva pra apontar contra um ambiente diferente:
```bash
OKR_BASE_URL=http://localhost:3000 claude-okr login
```
