---
name: distribution-strategy
description: Regras de distribuição do LowOpsCast baseadas em analytics reais (YouTube, TikTok, Instagram, LinkedIn) — prioridade por rede, matriz de cadência, horários, ranking de clips e orçamento de créditos. Use ao alterar schedule_matrix.py, o ranking de clips, o Judge, CTAs ou textos de post; ao decidir top-N, horário ou rede; e quando o usuário falar de cadência, horário de postagem, curadoria, viralização, CTA ou qual rede priorizar.
---

# Estratégia de distribuição

As decisões abaixo vêm de **dados medidos** do canal (jul/2026), não de benchmark genérico.
Ao mexer em `src/shared/schedule_matrix.py` (matriz, `_clip_score`, `_build_description`) ou em
`src/shared/judge.py`, mudanças que contrariem estes números precisam ser **justificadas
explicitamente ao usuário**, não aplicadas em silêncio.

## Hierarquia das redes (dado real)

| Rede | Alcance medido | Papel | Cortes funcionam? |
|---|---|---|---|
| YouTube Shorts | 76,6 mil views = **90,9% do canal** | 🥇 motor principal | sim |
| TikTok | 40,2 mil views (For You 88,9%) | 🥇 descoberta | sim |
| Instagram | Reels ~4% das views | 🥉 secundária | fraco — audiência vive em Stories |
| LinkedIn | 600 mil impressões (+119% YoY) | curado | **corte não; artigo técnico sim** |
| Facebook | — | baixa | opcional |

## Matriz de cadência

Fonte de verdade no código: `NETWORK_CONFIG` em `src/shared/schedule_matrix.py`.
Horários em **BRT** (`America/Sao_Paulo`), convertidos para UTC na saída.

| Rede | `top_n` | `hours_brt` | `gap_hours` | `days_only` |
|---|---|---|---|---|
| `YOUTUBE` | 99 (todos) | 12, 19 | 12 | qualquer |
| `TIKTOK_BUSINESS` | 99 (todos) | 12, 19 | 12 | qualquer |
| `INSTAGRAM_BUSINESS` | 6 | 12, 15 | 24 | qualquer |
| `LINKEDIN` | 3 | 8, 15 | 48 | ter/qua/qui |
| `FACEBOOK_PAGE` | 4 | 9, 12 | 24 | seg–sex |

**Confiança dos horários — importa para saber o que é ajustável:**

- **Instagram 12–15h: medido** (pico real do analytics). Não mudar sem dado novo.
- **YouTube:** o Studio reportou "dados insuficientes" para horário → valor é **semente**.
- **TikTok:** não coletado → **semente**.
- LinkedIn 8–9h / 15–17h: hipótese a testar.

Consumo da audiência: almoço (12–15h) e noite (19–22h). Público: BR, tech/DevOps, 96% masculino,
47,5% na faixa 25–34.

## Regra do funil (a mais importante)

Lives convertem **~80x mais inscritos por view** que Shorts (**4,49% vs 0,055%**).
Shorts trouxeram +42 inscritos; lives, +337.

→ **Todo corte precisa de CTA puxando o episódio completo.** Corte é topo de funil; a conversão
acontece na live/VOD. O CTA é anexado em `_build_description()`
(`src/shared/schedule_matrix.py`) — hoje `"🎙️ Episódio completo no YouTube @LowOps"`, sempre
concatenado, antes do truncamento em 2000 chars. Qualquer refatoração que possa emitir uma
`description` sem CTA é bug, não estilo.

## O que viraliza (cross-rede, observado)

Alimenta `curationPref` da OpusClip e a rubrica de curadoria (`src/shared/curation_rubric.md`):

1. **Carreira** — ATS, "Linux abre portas"
2. **Humor DevOps** — "Deploy 17h59", "QA de madrugada"
3. **Tech prático** — Keycloak, Terraform
4. **Curiosidade regional** — Pomerode, Floripa

Retenção média em Shorts: 35,2%.

## Ranking de clips — hierarquia de tiers

`_clip_score` usa três tiers **em ordem de confiança**; um tier superior sempre vence, então um
corte curto e ótimo ganha de um corte longo e raso:

1. **Score de conteúdo da curadoria** (`_content_score`) — payoff/insight real, não só fala limpa.
   Vem do **harness local dirigido pelo Claude Code** (`tools/curate/plan.py`, a partir do
   `verdicts.json` que eu escrevo aplicando `src/shared/curation_rubric.md`). O endpoint HTTP
   sozinho **não** anexa esse score — só o harness.
2. **Virality score nativo** da OpusClip, quando presente (não está no schema público — é sondado).
3. **`durationMs`** como proxy, quando não há score.

Não achate isso numa soma ponderada sem combinar com o usuário: a ordem de tiers é a decisão de
design.

O Azure AI Foundry (`gpt-5-mini`) foi removido em 2026-09-02; não existe mais judge LLM autônomo no
cloud. `JUDGE_MODE=rules_only` = só gate mecânico. A mecânica completa está na skill
`clip-curation-internals`.

## Orçamento (guarda-corpo)

- Plano **Pro Anual** — 3.600 créditos/ano (~40 episódios).
- 1 crédito = 1 min de vídeo **original**; episódio ~80 min ≈ 80 créditos.
- **Publicar não gasta crédito.** Só clipar.
- Storage da conta OpusClip em **~99/100 GB** → limpar projetos antigos antes de processar novos.
- Ao ligar a automação: **desligar o Auto-Import nativo** da OpusClip, senão clipa 2x e gasta
  crédito em dobro.

## ⚠️ Pendência: dados reais de set/2026 contradizem a hierarquia acima

Conectamos o **Buffer** (MCP, `mcp__buffer__*`) em 2026-09-06 pra analisar engajamento real —
canais: LinkedIn (`orafaelferreiraa`), YouTube (`LowOps Channel`), Instagram (`orafaelferreira1`).
TikTok **não está conectado** (Buffer free plan trava em 3 canais; TikTok é suportado, mas exigiria
upgrade ou trocar um canal existente).

**Últimos 30 dias (07/08–06/09/2026), por canal:**

| Métrica | LinkedIn (25 posts) | YouTube (10 posts) | Instagram (26 posts) |
|---|---:|---:|---:|
| Views | 887 | 216 | **14.609** |
| Reach | 25.279 | — (não retornado) | 8.538 |
| Taxa de engajamento | 1,8% | 4,17% | **7,61%** |

Isso **inverte** a hierarquia da tabela acima: Instagram apareceu como o canal mais forte (volume e
engajamento), YouTube com números baixíssimos. **Não tratar isso ainda como fato conclusivo:**

- O YouTube via Buffer devolveu bem menos métricas que os outros dois (sem `reach`/`impressions`) —
  sinal de que a integração Buffer↔YouTube pode não estar capturando os Shorts de verdade. Os 710
  posts do backlog (`schedule_queue.py --apply`, 2026-09-05/06) foram criados via **API da OpusClip
  direto, não pelo Buffer** — são pipelines diferentes. Os "10 posts" que o Buffer viu são de outra
  origem, não o canal inteiro.
- Antes de confiar nessa comparação, precisa investigar se é limitação de escopo/OAuth do Buffer
  com o YouTube, ou se reflete algo real.

**Decisão do usuário (2026-09-06): NÃO mudar a matriz de cadência agora.** Ele vai reanalisar o
Buffer **semana que vem** (~2026-09-13) com mais dados, porque os 710 posts já agendados via API não
dão pra apagar/reordenar em massa (`DELETE /publish-schedules/{scheduleId}` existe mas é 1-a-1, ver
skill `opusclip-api`) — qualquer mudança de prioridade só valeria pra conteúdo **futuro**, então não
há pressa. Antes de tocar em `NETWORK_CONFIG`/`NET` por causa disso, espere o usuário confirmar com
dado mais maduro E investigar o buraco de métricas do YouTube.

## Validação

```bash
pytest src/tests/test_schedule_matrix.py src/tests/test_judge.py -q
```

Contexto mais longo e histórico de decisões: `README.md` (§4–§6, §9) e `cortes-recomendados.md`.
