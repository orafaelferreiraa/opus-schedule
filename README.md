# LowOpsCast — Automação de Cortes e Distribuição Multi-Rede

Automação para transformar episódios do podcast **LowOpsCast** (YouTube [@LowOps](https://www.youtube.com/@LowOps))
em cortes verticais e distribuí-los **automaticamente** em YouTube Shorts, TikTok, Instagram, LinkedIn e
Facebook, usando **OpusClip** (clipping por IA) + **API REST** + **Azure Functions**.

> Status: **Etapa 1 (MVP) implementada e deployada** em Azure Functions (Flex Consumption).
> CI/CD verde (GitHub Actions + Terraform com state remoto). Etapas 2 e 3 pendentes.

## 1. Objetivo

Cortar cada episódio novo em ~10–15 clips virais e publicar/agendar nas redes **sem intervenção manual**,
com curadoria por tema + score, respeitando a cadência ideal de cada plataforma.

## 2. Descoberta-chave: são dois produtos diferentes

| | AgentOpus MCP (`api.opus.pro/api/agent-mcp`) | OpusClip REST API |
|---|---|---|
| O que faz | **Gera** vídeo do zero (text-to-video), clona voz | **Corta** vídeo longo em shorts (ClipAnything) |
| Serve para os cortes? | ❌ Não | ✅ **Sim** |
| Auth | OAuth | API Key |
| Uso no projeto | Fase 3 (capas/teasers) | Fase 2 (motor de corte) |

Ambos exigem plano **Pro+**.

## 3. Arquitetura

```mermaid
flowchart LR
  A[Novo episódio<br/>@LowOps] -->|RSS 15min| B[Timer Function]
  B --> C[POST /clip-projects<br/>+ webhook + brand template]
  C --> D[OpusClip corta<br/>~10-15 clips]
  D -->|webhook HMAC| E[HTTP Function]
  E --> F[GET clips<br/>+ virality score]
  F --> G[Curadoria: tema + score]
  G --> H[Roteamento por rede<br/>top-N + horário]
  H --> I[POST /publish-schedules<br/>escalonado + CTA]
  I --> J[YT · TikTok · IG<br/>LinkedIn · FB]
```

- **Trigger:** RSS do canal (`youtube.com/feeds/videos.xml?channel_id=...`) — grátis, sem API key.
  Observação: episódios são **lives agendadas**; o RSS só lista o VOD após a live terminar e ser processada
  (então o disparo acontece no momento certo, não no agendamento).
- **Hospedagem:** Azure Functions em **Flex Consumption (FC1)**, região East US 2 (~$0 ocioso).
  Hoje só o HTTP da Etapa 1 (`schedule-existing-clips`); Timer (RSS) + webhook chegam nas Etapas 2/3.
  Estado/idempotência em **Table Storage** (`lowopscaststate`) no storage compartilhado. Segredos
  injetados como app settings via `TF_VAR_*` (GitHub secrets) — ver §8.
- **Importante:** ao ligar o script, **desligar o Auto-Import nativo** (senão clipa 2x = gasta créditos em dobro).

## 4. Dados reais das redes (jul/2026) e insights cruzados

| Rede | Alcance | Cortes funcionam? | Converte seguidor? |
|---|---|---|---|
| YouTube Shorts | 76,6 mil views (**90,9% do canal**) | 🟢 Motor principal | Fraco (+42) |
| TikTok | 40,2 mil views (For You 88,9%) | 🟢 Descoberta | Fraco (2–4/post) |
| Instagram | Reels ~4% das views | 🔴 Ruim (audiência vive em Stories) | — |
| LinkedIn | 600 mil impressões (**+119%**) | 🟡 Corte não; **artigo técnico sim** | 🟢 Autoridade |

**Insights que guiam a automação:**

1. **Priorizar YT Shorts + TikTok** para os cortes; IG secundário; LinkedIn curado.
2. **Funil:** lives convertem **~80x mais inscritos por view** que Shorts (4,49% vs 0,055%).
   → Todo corte precisa de **CTA puxando o episódio completo**.
3. **Tipo de corte que viraliza** (cross-rede): carreira (ATS, "Linux abre portas"), humor DevOps
   ("Deploy 17h59", "QA de madrugada"), tech prático (Keycloak, Terraform), curiosidade regional
   (Pomerode/Floripa). → alimentar `curationPref`/prompt do OpusClip.
4. **Audiência:** BR, tech/DevOps, masculino 25–34. Consumo: almoço (12–15h) e noite (19–22h).

### 4.1. Números por rede (referência)

- **YouTube (@LowOps):** 84,3 mil views · 1.068 inscritos · Shorts 76,6 mil (90,9%) · Lives 7,5 mil (8,9%) ·
  Vídeos 178 (0,2%). Inscritos: Lives +337, Shorts +42. Retenção Shorts 35,2%. Demografia 96,1% M, 47,5% 25–34.
  "Quando os espectadores estão online": **sem dados suficientes**.
- **TikTok:** 40,2 mil views · For You 88,9% · 1,5 mil likes · followers/post baixo (alcance sem conversão).
- **LinkedIn:** 600.713 impressões (+119% YoY) · 14.322 engajamentos (2,4%) · top = artigos técnicos do blog
  (Terraform 15k/659, lab Azure 12k/545).
- **Instagram:** 7.313 seguidores · pico 12–15h · Stories dominam · Reels ~4% das views.

## 5. Matriz de cadência (dados reais + benchmark)

| Rede | Prioridade | Cortes/ep | Horário (BRT) | Base |
|---|---|---|---|---|
| YouTube Shorts | 🥇 Primária | Todos | 12–13h e 19–21h | 90,9% do canal (dado real) |
| TikTok | 🥇 Primária | Todos | 12–13h ou 19–21h | For You 88,9% (dado real) |
| Instagram | 🥉 Secundária | Top 4–6, 1/dia | **12–15h** ✅ | Analytics real (pico 15h) + Stories |
| LinkedIn | Curado | 2–3/semana | testar 8–9h e 15–17h | Priorizar artigo > corte |
| Facebook | Baixa | opcional | 9–12h úteis | Benchmark |

> Horário **medido** só do Instagram (12–15h). O YouTube não gerou relatório de horário ("dados
> insuficientes") e o TikTok não foi coletado — para essas redes o valor é semente e o serviço
> **auto-ajusta pela performance**.

## 6. Custos

- **Plano necessário:** Pro ($29/mês) — Starter não tem scheduler, LinkedIn/Facebook, nem API/MCP.
- **Créditos:** 1 crédito = 1 min de vídeo original. Pro = 300 créditos/mês (ou anual = 3.600/ano, ~50% mais barato/crédito).
- **Publicar não gasta crédito** em nenhuma rede — exceto X (não usado).
- Episódio ~80 min ≈ 80 créditos → **~4 eps inteiros/mês no Pro base**. Recomendado: **anual** + usar
  "Processing timeframe" nos episódios de 2h+.
- Atenção: storage está em **99,39/100 GB** — limpar projetos antigos antes de processar novos.

## 7. Referência técnica (OpusClip API)

- Criar projeto: `POST https://api.opus.pro/api/clip-projects` (Bearer API_KEY), body `{ videoUrl, brandTemplateId, curationPref, conclusionActions:[WEBHOOK] }`
- Buscar clips: `GET https://api.opus.pro/api/exportable-clips?q=findByProjectId&projectId=...` (traz virality score; `id` = `{projectId}.{clipId}` → usar clipId "bare")
- Contas sociais: `GET https://api.opus.pro/api/social-accounts?q=mine`
- Agendar: `POST https://api.opus.pro/api/publish-schedules` (`publishAt` UTC ISO 8601; `subAccountId` p/ FB/IG/LinkedIn)
- Plataformas: `YOUTUBE`, `TIKTOK_BUSINESS`, `INSTAGRAM_BUSINESS`, `LINKEDIN`, `FACEBOOK_PAGE`
- Webhook: assinado HMAC-SHA256(secretKey, body+salt) — validar `X-Opus-Signature`/`Salt`/`Timestamp`
- Limites: 30 req/min core; scheduler 1 req/s; cap 900 créditos/mês de API; concorrência 4 projetos
- OpenAPI: https://help.opus.pro/api-reference/openapi.json

## 8. Infraestrutura — modelo híbrido (reúso + stack próprio)

A infra é gerida por **Terraform** (`infra/terraform`) com **state remoto** no backend
`azurerm` (RG `rg-state-opus`, storage `stoopusstate`, container `statetf`). O stack **reutiliza**
recursos compartilhados do `rg-jsearch` (East US 2) via `data sources` e **cria** apenas o que é
específico do projeto.

**Reutilizado do `rg-jsearch` (somente leitura, via data sources):**

| Recurso | Tipo | Uso no projeto |
|---|---|---|
| `stjobfinderprodrandonix` | Storage Account | Runtime da função + Table `lowopscaststate` (idempotência) |
| `appi-jobfinder-prod` | Application Insights | Telemetria e logs (OpenTelemetry) |
| `acs-jobfinder-prod` + `orafaelferreira.com` | ACS Email | Notificações por e-mail (domínio já verificado) |
| `aif-jobfinder-prod-randonix` (`gpt-5-mini`) | AI Foundry / Azure OpenAI | Judge no modo `hybrid` (hoje dormente) |

**Criado por este stack (RG dedicado `rg-lowopscast-schedule`):**

| Recurso | Detalhe |
|---|---|
| App Service Plan próprio | **Flex Consumption (FC1)** — Flex é 1 app por plano, então não dá para reusar o plano do jobfinder |
| Function App `func-lowopscast-*` | Python 3.13, Linux, identidade gerenciada (System-Assigned) |
| Container `lowopscast-app-package` | Pacote de deployment, no storage compartilhado |

- **Segredos:** injetados como app settings via `TF_VAR_*` a partir de **GitHub secrets**
  (`OPUSCLIP_API_KEY`) e connection strings resolvidas dos data sources (ACS, Storage). **Não** usa
  Key Vault (o `kv-jf-prod-randonix` usa RBAC, que exigiria role assignments no CI) — migrar para KV
  fica como hardening futuro.
- **CI/CD:** `.github/workflows/ci-validate.yml` (testes + `terraform plan`) e `deploy.yml`
  (`terraform apply` + `func publish`). O SP do CI precisa de **Storage Blob Data Contributor** no
  `stoopusstate` (backend usa Azure AD; Owner não cobre o data plane de blob).
- **Custo:** ~$0/mês (FC1 por consumo; demais recursos já existiam).

## 9. Decisões fechadas

| Decisão | Escolha |
|---|---|
| Plano OpusClip | **Pro Anual** ($290/ano — 3.600 créditos/ano, ~40 eps) |
| Linguagem das Functions | **Python 3.13** |
| LinkedIn na automação | **Sim** — 2–3 clips curados/semana |
| Notificação | **E-mail** via ACS + domínio `orafaelferreira.com` |
| Trigger para lives | RSS detecta VOD automaticamente após live terminar |
| Storage | Limpar projetos antigos no dashboard OpusClip antes de reativar |
| Hospedagem | **Flex Consumption (FC1)** em plano próprio (Flex é 1 app/plano) — East US 2 |
| Reutilizar infra jobfinder | Sim, via `data sources` — Storage, App Insights, ACS+domínio, AI Foundry |
| State do Terraform | Backend remoto `azurerm` (`rg-state-opus`/`stoopusstate`/`statetf`) |
| Segredos | App settings via `TF_VAR_*`/GitHub secrets (sem Key Vault por ora) |
| Judge (curadoria LLM) | Dormente (`rules_only`); usa `gpt-5-mini` do Foundry existente ao ligar `hybrid` |

## 10. Roadmap em 3 etapas

### Etapa 1 — MVP com clips existentes *(✅ concluída — deployada)*
1. Function HTTP `schedule-existing-clips` lê clips **já processados** (via `GET /api/exportable-clips`).
2. Ranqueia top-N por virality score e aplica a matriz de cadência por rede. Observação: o schema
   público do `exportable-clips` **não expõe** um campo de score — o código sonda nomes conhecidos
   (`viralityScore` etc.) e cai para `durationMs` como proxy quando ausente.
3. Cria agendamentos via `POST /api/publish-schedules`, com **idempotência** em Table Storage
   (não reagenda o mesmo clip+rede) e resumo por e-mail (ACS).
4. Curadoria opcional pela **Judge** (`off`/`rules_only`/`hybrid`; hoje `rules_only`).
5. **Pendente:** validação funcional com um `collection_id` real do dashboard (dry-run).

### Etapa 2 — Episódios prontos ainda não publicados
1. Subir para o OpusClip os episódios gravados mas ainda não processados.
2. `POST /api/clip-projects` com URL do YouTube → clipagem → reutilizar pipeline da Etapa 1.
3. **Objetivo:** validar o fluxo completo de clipagem + agendamento.

### Etapa 3 — Automação completa com RSS *(futuro)*
1. Timer Function a cada 15 min monitora RSS do `@LowOps`.
2. Detecta novo VOD pós-live → dispara clipagem → webhook → curadoria → agendamento automático.
3. **Objetivo:** pipeline 100% hands-off a cada novo episódio.

## 11. Fontes (cadência)

- Hootsuite — *Best time to post 2025* (1M+ posts) e *How often to post 2025* (setor Technology).
- Buffer — *Best time to post 2026* (52M+ posts).
- Analytics próprios: YouTube Studio, Instagram, LinkedIn, TikTok (jul/2026).
