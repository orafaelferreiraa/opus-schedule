---
name: azure-diagnostics
description: Diagnóstico do LowOpsCast em produção no Azure — consultas KQL no Application Insights sobre as métricas e dimensões lowopscast.*, saúde do Function App em Flex Consumption, tabela de idempotência lowopscaststate e a cota de storage. Use ao investigar erro, latência, agendamento duplicado ou sumido em produção; ao inspecionar telemetria ou logs; e quando o usuário perguntar se o deploy está funcionando, o que aconteceu numa execução, ou pedir para olhar o Application Insights.
---

# Diagnóstico em produção

## Onde tudo mora

| O que | Nome real | Resource group |
|---|---|---|
| Function App (FC1) | `func-lowopscast-*` | `rg-lowopscast-schedule` |
| Application Insights | `appi-jobfinder-prod` | `rg-jsearch` |
| Storage (runtime + tabela) | `stjobfinderprodrandonix` | `rg-jsearch` |
| Tabela de idempotência | `lowopscaststate` | idem |
| State do Terraform | `stoopusstate` | `rg-state-opus` |
| AI Foundry (Judge) | `aif-jobfinder-prod-randonix` (`gpt-5-mini`) | `rg-jsearch` |

App Insights e Storage são **compartilhados** com o projeto jobfinder → **sempre filtrar** por
`lowopscast` / `cloud_RoleName == "func-lowopscast-prod"`, senão o resultado mistura os dois
sistemas.

Endpoints HTTP: `POST /api/schedule-existing-clips` e `POST /api/analyze-library`.

## Como executar as consultas

Preferir, nesta ordem:

1. **Servidor MCP `azure`** (read-only, se configurado) — ferramentas `monitor`, `storage`,
   `subscription_list`. Setup e credenciais: `docs/azure-mcp-inspection.md`.
2. **Azure CLI:**
   ```bash
   az monitor app-insights query \
     --app appi-jobfinder-prod -g rg-jsearch \
     --analytics-query "<KQL>" -o table
   ```

Se nenhum dos dois estiver autenticado, **não invente números** — entregue o KQL pronto para o
usuário rodar (`!` no prompt executa direto na sessão).

## KQL — consultas prontas

Erros recentes com o contexto de negócio:

```kql
traces
| where timestamp > ago(24h)
| where customDimensions.lowopscast_error != ""
| project timestamp, message,
          clip=tostring(customDimensions.lowopscast_clip_id),
          network=tostring(customDimensions.lowopscast_network),
          err=tostring(customDimensions.lowopscast_error)
| order by timestamp desc
```

Resultado por execução (planejado vs criado vs pulado vs falho):

```kql
customMetrics
| where timestamp > ago(7d)
| where name startswith "lowopscast."
| summarize total=sum(value) by name, bin(timestamp, 1d)
| order by timestamp desc
```

Latência do agendamento na OpusClip:

```kql
customMetrics
| where name == "lowopscast.opus.publish.latency"
| summarize p50=percentile(value,50), p95=percentile(value,95), n=count() by bin(timestamp, 1h)
```

Falhas de request na function:

```kql
requests
| where timestamp > ago(24h)
| where cloud_RoleName has "lowopscast"
| summarize total=count(), falhas=countif(success == false) by name, resultCode
```

Exceptions com stack:

```kql
exceptions
| where timestamp > ago(24h)
| where cloud_RoleName has "lowopscast"
| project timestamp, type, outerMessage, problemId
| order by timestamp desc
```

## Métricas emitidas (`src/shared/telemetry.py`)

Counters: `lowopscast.function.invocations` · `lowopscast.clips.found` ·
`lowopscast.schedules.planned` · `.created` · `.failed` · `.skipped` ·
`lowopscast.judge.clips.total` · `.approved` · `.review` · `.rejected`

Histogramas (ms): `lowopscast.execution.duration` · `lowopscast.judge.latency` ·
`lowopscast.opus.publish.latency`

Dimensões nos logs/spans: `lowopscast_network`, `lowopscast_clip_id`, `lowopscast_project_id`,
`lowopscast_publish_at`, `lowopscast_schedule_id`, `lowopscast_error`,
`lowopscast_publish_latency_ms`, `lowopscast_http_duration_ms`, `lowopscast_clips_count`.

Interpretação rápida: `planned - created - failed - skipped != 0` indica clip perdido no meio do
plano — investigar `filter_plan` e o loop de `create_schedules`.

## Idempotência (Table Storage)

Tabela `lowopscaststate` (override por `STATE_TABLE_NAME`). Chaves:
`PartitionKey = projectId` (ou `noproject`), `RowKey = {network}__{clipId}` — **dois**
underscores — sanitizado (`/ \ # ? \t \n \r` → `_`).

- `schedules.skipped` alto = está funcionando (não reagendou o mesmo clip+rede).
- Quer **reagendar de propósito** um clip? A entrada precisa ser removida da tabela — dizer isso ao
  usuário em vez de mexer no código de dedupe.
- `STATE_STORAGE_CONNECTION_STRING` ausente → o store desliga (`enabled == False`) e **nada é
  deduplicado**. Checar isso primeiro diante de agendamento duplicado.

## Cota de storage

O gargalo conhecido é a conta **OpusClip** (~99/100 GB), não o Azure. Sintoma: novos projetos de
clipagem falham. Correção é no dashboard da OpusClip (apagar projetos antigos), não no código.

No Azure, o container `lowopscast-app-package` guarda os pacotes de deploy — se crescer, listar e
limpar versões antigas.

## Config em produção

Segredos e config são **app settings** injetados pelo Terraform via `TF_VAR_*` a partir de GitHub
secrets — **não há Key Vault** (o `kv-jf-prod-randonix` usa RBAC e exigiria role assignments no CI).
Para conferir o que está aplicado de fato:

```bash
az functionapp config appsettings list -n <func-lowopscast-*> -g rg-lowopscast-schedule -o table
```

Variáveis que mudam comportamento: `JUDGE_MODE` (`off`/`rules_only`/`hybrid`), `JUDGE_THRESHOLD`,
`JUDGE_PROVIDER`, `JUDGE_AUTH_MODE`, `STATE_TABLE_NAME`, `NOTIFICATION_EMAIL_TO`,
`OPUSCLIP_ORG_ID`. Mudança de valor vai pelo Terraform, não por `az` — `az` é para **ler**.
