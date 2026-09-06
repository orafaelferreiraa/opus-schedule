# OpusClip API — referência de endpoints

## Conteúdo

- Autenticação
- Contas sociais (`/social-accounts`)
- Coleções (`/collections`)
- Projetos de corte (`/clip-projects`)
- Clips exportáveis (`/exportable-clips`)
- Agendamento (`/publish-schedules`)
- Webhook (validação HMAC)
- Plataformas suportadas
- Códigos de erro observados

## Autenticação

```
Authorization: Bearer <OPUSCLIP_API_KEY>
Content-Type: application/json
x-opus-org-id: <OPUSCLIP_ORG_ID>     # opcional, só quando definido
```

Requer plano **Pro+**. Starter não expõe API, scheduler, LinkedIn nem Facebook.

## Contas sociais

```
GET /social-accounts?q=mine
```

Devolve as contas conectadas. Cada item traz o `postAccountId` (usado no agendamento) e, para
Facebook/Instagram/LinkedIn, a lista de sub-contas (`subAccountId` = página/perfil de destino).

Use este endpoint para descobrir IDs reais — nunca chumbe `postAccountId` no código.

## Coleções

```
GET /collections?q=mine
```

Coleções da conta. O `collection_id` é o que o endpoint `schedule-existing-clips` recebe para o
fluxo da Etapa 1.

## Projetos de corte

```
POST /clip-projects
{
  "videoUrl": "https://www.youtube.com/watch?v=...",
  "brandTemplateId": "<id do template de marca>",
  "curationPref": "<prompt/preferência de curadoria>",
  "conclusionActions": ["WEBHOOK"]
}
```

Cria o projeto e dispara a clipagem (**gasta créditos** = duração do vídeo em minutos).
`conclusionActions: ["WEBHOOK"]` faz a OpusClip chamar o webhook ao terminar.

```
GET /clip-projects?q=mine
```

Lista todos os projetos. **Não documentado no OpenAPI** (que só expõe `POST` e `GET` por id), mas
funciona e devolve o envelope `{data:{list:[...]}}`. Cada item traz `projectId`, `createdAt`,
`updatedAt` e `sourceInfo.title`. Usado por `list_projects()` no relatório de biblioteca.

## Clips exportáveis

```
GET /exportable-clips?q=findByProjectId&projectId=<id>&pageNum=1&pageSize=50
GET /exportable-clips?q=findByCollectionId&collectionId=<id>&pageNum=1&pageSize=50
```

Paginação: incrementar `pageNum` até a página vir vazia ou com menos de `pageSize` itens
(`_paginate_clips` faz isso).

Campos úteis por clip:

| Campo | Observação |
|---|---|
| `id` | **composto**: `{projectId}.{clipId}` |
| `projectId` | usar direto no agendamento |
| `durationMs` | proxy de score quando não há score real |
| `title` / texto / transcrição | insumo do Judge LLM e do CTA |
| `viralityScore` (e variantes) | **não garantido** no schema público — sondar, não assumir |

### Forçar layout split

```
PUT /exportable-clips/{projectId}.{clipId}
{
  "renderPref": {
    "enableSplitLayout": true,
    "enableFillLayout": false,
    "enableFitLayout": false,
    "disableFillLayout": true,
    "disableFitLayout": true,
    "layoutAspectRatio": "portrait"
  }
}
```

Só campos do `RenderPreferenceDto`. Resposta pode vir com corpo vazio — o cliente trata
(`_put` devolve `""`).

## Agendamento

```
POST /publish-schedules
{
  "projectId": "<projectId>",
  "clipId": "<clipId BARE, sem prefixo>",
  "postAccountId": "<de /social-accounts>",
  "subAccountId": "<obrigatório p/ FB, IG, LinkedIn>",
  "postDetail": {
    "title": "<máx 100 chars>",
    "mediaType": "video",
    "custom": { "description": "<descrição + CTA para o episódio completo>" }
  },
  "publishAt": "2026-07-28T15:00:00Z"
}
```

- `publishAt`: **UTC**, ISO 8601. Aceita horário **quase imediato** (testado com agora+5 min em
  2026-09-06 — publicou normal), útil para tapar buraco de slot sem esperar a próxima janela.
- Rate limit **1 req/s** — dormir ≥1,1 s entre chamadas.
- Resposta: **201** com `{"data":{"scheduleId","postId","hasConflict","publishAt"}}` — o
  `hasConflict` avisa se o horário colide com outro agendamento da mesma conta.
- Não gasta crédito.
- **Limite diário observado: 429 `"api rate limit exceeded", operation:"publish", limit:500,
  window:"DAY"`** (achado 2026-09-05, aplicando um backlog de ~700 de uma vez). Não documentado
  no OpenAPI. Ficar com headroom (ex.: ≤450/execução), não tentar os 500 exatos.

### Listar agendamentos (não documentado, mas existe)

```
GET /publish-schedules?q=byPage
→ {"data": {"data": [ {scheduleId, extUserId, extOrgId, platform, postDetail:{title,thumbnailUrl}, publishAt}, ... ],
            "meta": {"page", "nextPage", "total"}}}
```

Descoberto 2026-09-06: `GET /publish-schedules` sem `q` dá 400, mas o corpo revela os valores
aceitos (`"Supported values: byPage, findByProjectAndClip"`). `q=byPage` devolveu os **471
agendamentos da conta inteira numa chamada só** (sem truncar — `page`/`pageSize` testados não
mudaram nada). **Não tem `clipId`/`projectId`** — só dá pra cruzar com os clips do projeto por
`platform` + `postDetail.title` (+ `publishAt`). É a forma de **auditar de verdade** o que está
agendado (em vez de confiar só no ledger local) e achar duplicatas reais.

### Apagar um agendamento (não documentado, mas existe)

```
DELETE /publish-schedules/{scheduleId}
```

Descoberto 2026-09-06 e **confirmado com `scheduleId` reais no mesmo dia**: devolve **200
`{"data":{}}`** e o agendamento some do `GET ?q=byPage` (validado apagando 3 agendamentos —
2 duplicatas em YouTube/TikTok e 1 do Instagram que foi remanejado). Com ID falso devolve 400
`{"errorMessage":"Schedule task not found","errorName":"BadRequestError"}`. `scheduleId` vem do
item retornado por `GET /publish-schedules?q=byPage` (ex.: `"1788615219038dgRU-YOUTUBE"`).
Não existe update/move: para remanejar um post é **DELETE + POST novo**, 1 a 1.
Variante `DELETE /publish-schedules?scheduleId=...` NÃO funciona sozinha — exige também
`source` e `projectId` como query params (`"source and projectId query params are required"`).

## Webhook

Assinatura: **HMAC-SHA256(secretKey, body + salt)**. Validar os headers:

- `X-Opus-Signature`
- `X-Opus-Salt`
- `X-Opus-Timestamp`

Comparar em tempo constante (`hmac.compare_digest`) e rejeitar timestamp fora de janela.
Chega na Etapa 3 (ainda não implementado).

## Plataformas suportadas

`YOUTUBE` · `TIKTOK_BUSINESS` · `INSTAGRAM_BUSINESS` · `LINKEDIN` · `FACEBOOK_PAGE`

(Strings exatas — são as chaves de `NETWORK_CONFIG` em `src/shared/schedule_matrix.py`.)

## Códigos de erro observados

| Status | Causa típica |
|---|---|
| 400 | `clipId` composto onde se espera o bare; campo fora do DTO em `renderPref` |
| 401 | `OPUSCLIP_API_KEY` ausente/expirada, ou plano sem API |
| 429 | rate limit — 1 req/s no scheduler, 30 req/min no core |
| 5xx | transiente; o lote registra `ok=False` e segue |

O corpo do erro é logado truncado em 2048 chars como `lowopscast_error` no Application Insights.
