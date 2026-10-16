# Leve OKR — Claude Code e Codex

Plugin para consultar e gerenciar tarefas, metas e check-ins no [Leve OKR](https://okr.leveinovacao.com.br) via linguagem natural. Os dois clientes compartilham a mesma skill e o mesmo helper.

Requer **Python 3.9+** e acesso ao servidor do Leve OKR. Funciona em Windows, Linux e macOS, sem pacotes pip, Bash ou curl. Só contas `@leveinovacao.com.br` podem autorizar o acesso.

## Claude Code

Em uma sessão do Claude Code:

```text
/plugin marketplace add Leve-Inovacao-Estrategica/claude-okr-plugin
/plugin install okr@leve
```

A skill executa o helper pelo caminho do pacote; a instalação não adiciona comandos ao PATH automaticamente.

## Codex — instalação como skill

Clone este repositório e, na raiz dele, execute:

```powershell
python scripts/install-codex-skill.py
```

Isso copia a skill completa, incluindo o helper, para `.agents/skills/okr` no diretório atual. Abra o projeto no Codex e use `$okr` ou faça um pedido sobre o Leve OKR. Reabra o Codex se a skill não aparecer.

Para usar em todos os projetos, instale na pasta pessoal de skills:

```powershell
python scripts/install-codex-skill.py --dest "$HOME/.agents/skills"
```

Em Linux/macOS, use `python3` nos comandos. Para instalar em outro projeto, passe `--dest /caminho/do/projeto/.agents/skills`. Para atualizar uma instalação existente, repita o comando com `--force`.

O pacote também inclui `plugins/okr/.codex-plugin/plugin.json`, com `skills: "./skills/"`, para distribuição como plugin do Codex. A raiz desse pacote é **`plugins/okr`**, não a raiz deste repositório. O marketplace `.claude-plugin/marketplace.json` é específico do Claude Code; a instalação direta da skill acima dispensa um marketplace do Codex.

Referências: [skills locais no Codex](https://learn.chatgpt.com/docs/build-skills) e [empacotamento de plugins](https://developers.openai.com/plugins/build/plugins).

## Uso

| Você diz | O plugin faz |
|---|---|
| "quais tarefas pendentes do projeto X?" | Lista tarefas |
| "como está o projeto X?" | Resume status e atrasos |
| "como estão as metas do X?" | Mostra progresso e metas em risco |
| "adiciona tarefa no projeto X: revisar plano até sexta" | Resolve projeto e meta, mostra preview e pede confirmação |
| "marca a tarefa 123 como concluída" | Consulta, mostra preview e pede confirmação |

Criar/editar tarefas, editar/excluir ações e fazer check-ins MANUAL exigem confirmação. Registrar ações executadas e notas de check-in AUTO segue as exceções documentadas na skill.

Na primeira operação sem credenciais, o assistente gera um link, mostra-o no chat e aguarda você autorizar com a conta Google da Leve. Nenhum token aparece no chat.

## Comandos manuais

Na raiz do repositório:

```powershell
python plugins/okr/skills/okr/scripts/okr.py --help
python plugins/okr/skills/okr/scripts/okr.py login "Codex"
python plugins/okr/skills/okr/scripts/okr.py whoami
python plugins/okr/skills/okr/scripts/okr.py call GET /api/agent/projects
python plugins/okr/skills/okr/scripts/okr.py logout
```

O login manual tenta abrir o navegador padrão. O assistente usa `login-start "Codex"` ou `login-start "Claude Code"`, mostra a `verification_uri` retornada e só então executa `login-wait`. `whoami` valida o token e conta projetos; não retorna o email do usuário.

Para enviar JSON no PowerShell, salve o payload em UTF-8 e passe `@arquivo.json` como argumento literal:

```powershell
python plugins/okr/skills/okr/scripts/okr.py call POST /api/agent/tasks '@payload.json'
```

O argumento `-` lê JSON de stdin. `upload <arquivo>` envia uma imagem e retorna o JSON de URL/HTML. Erros HTTP preservam o corpo da resposta e retornam exit 1; falta de autenticação retorna exit 2. O helper não repete escritas automaticamente.

O atalho legado `plugins/okr/bin/claude-okr` continua funcionando em ambientes Bash e delega ao helper Python. Use seu caminho explícito ou configure o PATH manualmente.

## Credenciais e configuração

Os dois clientes compartilham `~/.config/leve-okr/credentials`, ou `$XDG_CONFIG_HOME/leve-okr/credentials` quando configurado. O helper lê o formato legado `OKR_TOKEN=...` sem executar código do arquivo. O código pendente fica em `pending-device-code` e é removido após aprovação, negação ou expiração pelo servidor.

Em Linux/macOS, os arquivos usam permissões `600`. Em Windows, o acesso depende das ACLs do diretório do usuário; `chmod` não configura ACLs. Não coloque credenciais no repositório nem exiba seu conteúdo no chat. Para revogar o token no servidor, peça ao administrador a revogação no Leve OKR.

Variáveis opcionais:

| Variável | Uso |
|---|---|
| `OKR_BASE_URL` | Servidor (default: `https://okr.leveinovacao.com.br`) |
| `XDG_CONFIG_HOME` | Diretório base das credenciais |
| `OKR_NO_BROWSER=1` | Exibe o link sem abrir navegador; recomendado no uso pelo assistente |
| `CLAUDE_OKR_NO_BROWSER=1` | Alias legado de `OKR_NO_BROWSER` |

PowerShell: `$env:OKR_BASE_URL = "http://localhost:3000"`. Bash: `export OKR_BASE_URL=http://localhost:3000`.

Projetos, metas e responsáveis são resolvidos pela API. O plugin não ativa portais públicos. O campo `origin` permanece `claude-code-plugin` nos dois clientes por compatibilidade com o backend; o nome do cliente é informado no login. Não foi presumido suporte do servidor a um novo valor de `origin`.

## Validação local

```powershell
python -m unittest discover -s tests -v
```

Os testes usam respostas simuladas e diretórios temporários; não acessam a API de produção nem credenciais pessoais.
