# Habilitar o Azure MCP para inspeção ao vivo (read-only)

Objetivo: dar ao servidor **azure** do Docker MCP credenciais Azure para inspecionar o
ambiente do LowOpsCast ao vivo — uso do storage (o gargalo de **99,39/100 GB**), saúde do
Function App e telemetria no Application Insights — sem `az login` interativo dentro do container.

O servidor `azure` (imagem oficial `mcr.microsoft.com/azure-sdk/azure-mcp`) autentica via
`DefaultAzureCredential`, que lê as env vars `AZURE_TENANT_ID` / `AZURE_CLIENT_ID` /
`AZURE_CLIENT_SECRET` (`EnvironmentCredential`). O catálogo padrão do Docker MCP **não** mapeia
essas env vars, então sobrescrevemos o servidor por um **catálogo customizado** e preenchemos
com um **service principal read-only** dedicado.

> Todas as roles abaixo são **somente leitura**. Nada aqui concede escrita/deploy.

## Recursos-alvo (nomes reais deste projeto)

| Recurso | Nome | Resource group |
|---|---|---|
| Storage compartilhado (runtime + tabela idempotência) | `stjobfinderprodrandonix` | `rg-jsearch` |
| Application Insights (telemetria) | `appi-jobfinder-prod` | `rg-jsearch` |
| Function App + plano FC1 | `func-lowopscast-*` / `plan-lowopscast-schedule` | `rg-lowopscast-schedule` |
| Storage do state remoto Terraform | `stoopusstate` | `rg-state-opus` |

## Passo 1 — Criar o service principal read-only (você executa)

Requer Azure CLI logado com permissão para criar SP e atribuir roles. Rode no seu terminal
(no Claude Code dá para usar o prefixo `!` para executar direto na sessão):

```bash
# Defina a subscription (o mesmo valor do secret AZURE_SUBSCRIPTION_ID do GitHub)
export SUB_ID="<sua-subscription-id>"
az account set --subscription "$SUB_ID"

RG_JSEARCH="/subscriptions/$SUB_ID/resourceGroups/rg-jsearch"
RG_LOWOPS="/subscriptions/$SUB_ID/resourceGroups/rg-lowopscast-schedule"
RG_STATE="/subscriptions/$SUB_ID/resourceGroups/rg-state-opus"

# Cria o SP com Reader nos 3 resource groups do projeto (ARM read + métricas)
az ad sp create-for-rbac \
  --name "sp-lowopscast-mcp-readonly" \
  --role "Reader" \
  --scopes "$RG_JSEARCH" "$RG_LOWOPS" "$RG_STATE"
# → guarde o JSON: appId (client_id), password (client_secret), tenant (tenant_id)

APP_ID="<appId-do-output-acima>"

# Telemetria do Application Insights / Log Analytics (queries KQL)
az role assignment create --assignee "$APP_ID" \
  --role "Monitoring Reader" --scope "$RG_JSEARCH"

# Leitura da tabela de idempotência lowopscaststate (data plane, somente leitura)
az role assignment create --assignee "$APP_ID" \
  --role "Storage Table Data Reader" \
  --scope "$RG_JSEARCH/providers/Microsoft.Storage/storageAccounts/stjobfinderprodrandonix"
```

Anote os três valores não-secretos (`tenant`, `appId`, `SUB_ID`) e o `password` (secreto).

## Passo 2 — Gerar o catálogo customizado do servidor `azure`

O script abaixo lê o snapshot **oficial** do servidor `azure` já presente no seu profile e
reescreve-o adicionando os blocos `env` + `secrets` — **preservando a lista de tools 1:1**
(nada de digitar tool por tool). Rode a partir da raiz do repo:

```bash
DOCKER="/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe"
CATDIR="$HOME/.docker/mcp/catalogs"          # no Windows: C:\Users\<voce>\.docker\mcp\catalogs
mkdir -p "$CATDIR"

"$DOCKER" mcp profile server ls --filter profile=profile --format json \
| python3 -c "
import sys, json, yaml
d = json.load(sys.stdin)
srv = next((s['snapshot']['server']
            for prof in d for s in prof.get('servers', [])
            if s.get('snapshot', {}).get('server', {}).get('name') == 'azure'), None)
assert srv, 'servidor azure não encontrado no profile'
srv['env'] = [
    {'name': 'AZURE_TENANT_ID',       'value': '{{azure.tenant_id}}'},
    {'name': 'AZURE_CLIENT_ID',       'value': '{{azure.client_id}}'},
    {'name': 'AZURE_SUBSCRIPTION_ID', 'value': '{{azure.subscription_id}}'},
]
srv['secrets'] = [{'name': 'azure.client_secret', 'env': 'AZURE_CLIENT_SECRET'}]
with open('$CATDIR/azure-sp.yaml', 'w', encoding='utf-8') as f:
    yaml.safe_dump(srv, f, sort_keys=False, allow_unicode=True, width=100)
print('catálogo escrito:', '$CATDIR/azure-sp.yaml', '| tools preservados:', len(srv.get('tools') or []))
"
```

## Passo 3 — Preencher config + secret e religar o servidor

```bash
DOCKER="/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe"

# Valores NÃO-secretos como config do profile
"$DOCKER" mcp profile config profile --set \
  azure.tenant_id="<tenant>" \
  azure.client_id="<appId>" \
  azure.subscription_id="<SUB_ID>"

# O client_secret via keychain (nunca em texto no repo/chat) — lê do stdin
printf '%s' "<password>" | "$DOCKER" mcp secret set azure.client_secret

# Aponta o profile para o servidor azure do catálogo customizado (sobrescreve o padrão)
"$DOCKER" mcp profile server add profile --server file://azure-sp.yaml
```

No Claude Code, rode `/mcp` (ou reinicie a sessão) para religar o gateway MCP e recarregar o
servidor `azure` com as credenciais.

## Passo 4 — Verificação (eu executo)

Quando terminar os passos 1–3, me avise. Vou validar com chamadas read-only e trazer o
diagnóstico:

- `subscription_list` → confirma auth.
- `storage` → uso real de `stjobfinderprodrandonix` (o problema dos 99 GB) e listagem de blobs
  do container de deploy `lowopscast-app-package`.
- `monitor` / Application Insights → erros e latência de `schedule-existing-clips` e
  `publish-schedules` (as métricas OTEL `lowopscast.*` emitidas por `telemetry.py`).
- tabela `lowopscaststate` → quantos agendamentos já foram deduplicados.

## Reverter

```bash
DOCKER="/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe"
"$DOCKER" mcp secret rm azure.client_secret
"$DOCKER" mcp profile config profile --del azure.tenant_id azure.client_id azure.subscription_id
rm "$HOME/.docker/mcp/catalogs/azure-sp.yaml"
# e apague o SP no Azure:
az ad sp delete --id "<appId>"
```
