---
name: opusclip-api
description: Contrato e armadilhas da OpusClip REST API (api.opus.pro) usada por este projeto — clip-projects, exportable-clips, publish-schedules, social-accounts, collections, webhook HMAC, rate limits e custo em créditos. Use ao escrever, revisar ou depurar qualquer código que chame a OpusClip (src/shared/opus_client.py), quando uma chamada retornar 4xx/5xx, ou quando o usuário mencionar OpusClip, clip, corte, agendamento, publish-schedule, virality score ou créditos.
---

# OpusClip REST API

Cliente único do projeto: `src/shared/opus_client.py`. **Toda** chamada nova entra lá — não crie
`httpx.Client` avulso em outro módulo (perde telemetria, rate limit e tratamento de erro).

Base: `https://api.opus.pro/api` · Auth: `Authorization: Bearer $OPUSCLIP_API_KEY`
(+ header opcional `x-opus-org-id` de `$OPUSCLIP_ORG_ID`).

## Armadilhas que já custaram tempo neste repo

Leia antes de mexer em payload ou parsing:

1. **Envelope de listagem.** Respostas de lista vêm como `{"data": {"list": [...], "total", "limit"}}`
   — nunca como array cru. Use `_extract_list()`, que também tolera `{"data": [...]}` e array puro.
2. **`id` do clip é composto.** `exportable-clips` devolve `id = "{projectId}.{clipId}"`. O
   `POST /publish-schedules` exige o **`clipId` "bare"** (sem o prefixo) em `clipId`, e o
   `projectId` em campo separado. Mandar o id composto → 4xx.
   Exceção: `PUT /exportable-clips/{id}` usa o **id composto**.
3. **`viralityScore` não está no schema público.** O OpenAPI de `exportable-clips` não expõe. O
   código sonda `_VIRALITY_FIELDS` e cai para `durationMs` como proxy. Não assuma que o campo
   existe; veja a hierarquia de tiers em `_clip_score` (`src/shared/schedule_matrix.py`).
4. **`PUT /exportable-clips/{id}` REPLACES o `renderPref` inteiro** — mande o objeto completo, não
   parcial (parcial apaga os outros campos, ex.: layout). Verificado empiricamente 2026-09-03
   (corrige nota antiga que dizia que `removeFillerWord`/`removePause` davam 400): esses campos
   EXISTEM, mas como **objetos**, não booleanos:
   - `removeFillerWord: {enabled: bool, selectedFillers: [str, ...]}` — o template atual vem
     `enabled:true` mas `selectedFillers:[]` (vazio → **não corta muletas PT-BR**; por isso o
     filler% dos cortes segue alto). Preencher `selectedFillers` (ex.: `["né","tipo","aí"]`) é aceito.
   - `removePause: {enabled: bool, pauseDuration: float}` — já ligado no template; corta ~16s/corte
     de pausa no render (por isso `durationMs` < span do `timeRanges`, e o `__silence` sumiu do texto).
   - **`timeRanges` É gravável** (a doc/OpenAPI diz "read-only" — falso): `[[startMs, endMs], ...]`.
     PUT com timeRanges editado retorna 200 e persiste.
   `OpusClient._SPLIT_RENDER_PREF` ainda serve pra forçar layout split; para fillers/in-out, mande o
   renderPref completo do próprio clip com os campos ajustados.
   **PORÉM — pegadinha grande:** setar esses campos **não re-renderiza o clip**. Não há endpoint de
   re-render por clip (o OpenAPI só tem `POST /collections/{id}/export`, e a conta pode não ter
   coleção). Edição via API é **preferência de render**: só materializa quando o clip é renderizado
   de novo (export de coleção ou, presumivelmente, no publish). Confirmado: após PUT, `durationMs`/
   `text` não mudaram em 75s de polling. Não prometa "editei o corte" — você editou a *preferência*.
5. **`publishAt` é UTC ISO 8601.** A matriz de cadência raciocina em BRT
   (`America/Sao_Paulo`) e converte na saída — nunca mande horário local.
6. **`subAccountId` é obrigatório** para `FACEBOOK_PAGE`, `INSTAGRAM_BUSINESS` e `LINKEDIN`
   (páginas/perfis dentro da conta). YouTube e TikTok não usam.
7. **`postDetail.title` tem limite de 100 chars** — o cliente já trunca; mantenha o truncamento
   se refatorar.

## Limites (respeitar, não "tentar")

| Limite | Valor | Onde é tratado |
|---|---|---|
| Core endpoints | 30 req/min | paginação de `_paginate_clips` |
| `publish-schedules` | **1 req/s** | `_SCHEDULER_RATE_LIMIT_S = 1.1` em `create_schedules` |
| Cota de API | 900 créditos/mês | orçamento, não código |
| Projetos concorrentes | 4 | relevante na Etapa 2/3 |

**Créditos:** 1 crédito = 1 min de vídeo original. Só **clipar** gasta; **publicar/agendar não gasta**
(exceto X, não usado). Episódio de ~80 min ≈ 80 créditos. Antes de sugerir reprocessar um episódio,
lembre que o storage da conta está no limite (~99/100 GB) — limpar projetos antigos vem primeiro.

## Erros em lote

O padrão do projeto é **falha individual não aborta o lote**: cada item devolve
`{"ok": False, "error": ...}` e o loop continua (`create_schedules`,
`prepare_clips_for_split_layout`). Preserve esse contrato — os testes e o e-mail de resumo
dependem dele.

## Referência completa de endpoints

Payloads, query params e formato de resposta de cada rota: veja
[reference/endpoints.md](reference/endpoints.md).

Fonte canônica upstream: `https://help.opus.pro/api-reference/openapi.json` — busque lá antes de
adivinhar um campo, e prefira `WebFetch` a inventar.

## Validação

Mudou `opus_client.py` ou o payload de agendamento?

```bash
pytest src/tests/test_opus_client.py src/tests/test_function_app.py -q
```

Rodar da **raiz** do repo (`pyproject.toml` já coloca `src/` no `sys.path`). Sem ambiente pronto:
`python3 -m venv .venv && .venv/bin/pip install -r src/requirements.txt pytest`.
