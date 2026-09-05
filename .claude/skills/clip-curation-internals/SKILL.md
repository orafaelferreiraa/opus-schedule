---
name: clip-curation-internals
description: Mecânica interna da curadoria de cortes — os gates mecânicos determinísticos (shared/judge.py no agendamento e shared/clip_quality.py no relatório) e o harness local de curadoria de CONTEÚDO dirigido pelo Claude Code (tools/curate/, rubrica em src/shared/curation_rubric.md). Use ao mexer em judge.py, clip_quality.py, library_report.py, na rubrica de curadoria, nos gates mecânicos, nas env vars JUDGE_*, ou quando o usuário falar de judge, curadoria, aprovar/reprovar corte, score de conteúdo, verdicts.json ou o projeto do Paulo.
---

# Mecânica da curadoria

`distribution-strategy` cobre a política editorial (o que viraliza, cadência, ordem dos tiers, CTA).
Esta skill cobre a **mecânica**: quem filtra o quê, e onde a substância de conteúdo é julgada.

## O modelo atual: gate mecânico no código + curadoria de conteúdo local com o Claude

Desde 2026-09-02 o **Azure AI Foundry (`gpt-5-mini`) foi arrancado** de `judge.py`,
`clip_quality.py` e do Terraform. Não há mais chamada de LLM remoto em lugar nenhum do código.
A verificação agora tem **duas camadas separadas**:

1. **Gate mecânico determinístico** (no código, roda no cloud e localmente) — limpeza de fala e
   duração. Só isso corre dentro do Function App.
2. **Curadoria de CONTEÚDO** (payoff/insight) — feita **localmente pelo Claude Code** via o harness
   em `tools/curate/`. Eu leio as transcrições e aplico a rubrica única em
   `src/shared/curation_rubric.md`, produzindo `verdicts.json`. Não é autônoma no cloud.

**Consequência de design:** o modo `hybrid` não existe mais; `JUDGE_MODE` só assume `off` ou
`rules_only`, e `rules_only` significa **apenas gate mecânico**. Quem pedir "ligar o judge LLM" ou
"deixar o judge mais rigoroso" está falando da **rubrica** (`curation_rubric.md`) e do harness, não
de env var nem de deployment.

## O harness local (`tools/curate/`)

Fluxo em três passos — os passos 1 e 3 são scripts; o passo 2 sou eu:

1. **`prep.py`** — acha o projeto (`--title` casa no `sourceInfo.title`, ou `--project-id`), puxa os
   clips via `OpusClient.get_clips_by_project`, usa a transcrição nativa `clip["text"]` (todos os
   clips já trazem; **não precisa de whisper**), roda o gate mecânico (reaproveita
   `extract_speech_signals` + `rule_verdict` de `clip_quality.py`) e escreve
   `review/<projectId>/clips.json` + `transcripts.md`.
2. **Eu (Claude) julgo** cada corte pela rubrica e escrevo `review/<projectId>/verdicts.json`:
   `[{id, approve, final_score, content_flags, speech_flags, reason}]`.
3. **`plan.py`** — funde os veredictos, marca `recommended = gate_passed AND approve`, anexa
   `_content_score = final_score` aos aprovados, roda `build_schedule_plan` e imprime o **plano em
   dry-run** (não chama `create_schedules`) + renderiza `report.md` no estilo de
   `cortes-recomendados.md`.

`review/**/clips.json` e `transcripts.md` são gitignored (volumosos, regeneráveis); `verdicts.json`
e `report.md` podem ser versionados como entregável.

```bash
python3 tools/curate/prep.py --title Paulo     # projeto piloto: P3083113Va84 (#55, Paulo Alves)
# … eu escrevo verdicts.json …
python3 tools/curate/plan.py --project-id P3083113Va84
```

## A rubrica é fonte ÚNICA agora

Antes a mesma rubrica editorial vivia duplicada em dois prompts de LLM. Agora ela vive **só** em
`src/shared/curation_rubric.md` (9 payoffs, incl. gestão de pessoas/liderança; "fala limpa NÃO
basta"; **reprovar SEMPRE crítica
negativa a concorrente/fornecedor nomeado** → flag `critica_concorrente_nomeado`; na dúvida,
reprova). Ajuste de critério = editar **esse arquivo**, e eu o sigo no passo 2.

## Modos do judge mecânico (`shared/judge.py`)

`function_app.py` liga o gate com `if judge_settings.mode == "rules_only"`.

- `rules_only` — **modo de produção** (`main.tf`). Só as hard rules; devolve `final_score` uniforme
  **100** (não ordena nada — o ranking real usa `_content_score` do harness).
- qualquer outro valor (`off`, typo, etc.) — cai no ramo `source="disabled"`: **aprova todos os
  clips sem filtrar**. Não há log nem erro. Se a curadoria "não está filtrando", conferir
  `JUDGE_MODE` é o primeiro passo.

Decisão do judge mecânico é binária: **APPROVE** (passou nas hard rules) ou **REJECT** (falhou).
Não há mais faixa de `REVIEW` (isso vinha do score do LLM, que não existe). `include_review_in_dry_run`
segue sendo lido mas é inócuo, já que REVIEW nunca é produzido.

## Os dois gates mecânicos medem coisas diferentes — armadilha que permanece

**`judge.py:_run_hard_rules`** — o texto que ele mede é `title + description`, **não a
transcrição**. Um corte com transcrição rica e metadados vazios é **hard-rejected por
`text_too_short`**. Duração aceita: `JUDGE_MIN_DURATION_MS`..`JUDGE_MAX_DURATION_MS` (10 s–180 s por
default). São os únicos gates no caminho de agendamento.

**`clip_quality.extract_speech_signals` + `rule_verdict`** — medem a transcrição de verdade:
`__silence` = pausas, sufixo `--` = cortes de palavra, repetição imediata, densidade de filler, e
duração 20 s–90 s (`DEFAULT_RULES`). É o gate usado pelo relatório **e** pelo harness (`prep.py`).

`DEFAULT_RULES` foi **calibrado na distribuição real de 344 cortes** — não mexer nos números sem
redistribuir. A lista `_FILLERS` é **PT-BR e específica do apresentador** (`"cara"` está lá porque é
tique dele). Trocar por tokenizer genérico ou filler em inglês zera os sinais e tudo passa.

## Anti-padrão documentado: os scores nativos da OpusClip

`raw` / `hook` / `coherence` / `connection` são reportados mas **excluídos de propósito de todo
gate**. Motivo verificado: a OpusClip é "torcedora" — dá nota alta a qualquer anedota bem contada,
mesmo sem substância. Quem for "melhorar o gate" vai querer usá-los primeiro; é justamente o que não
se faz. `test_library_report.py` (`test_mechanical_gate_ignores_opus_native_scores`) trava isso.

## A ponte para o ranking: `_content_score`

`_content_score` (tier 2 de `schedule_matrix._clip_score`) é a melhor sinalização de viralidade.
Hoje ela é anexada **pelo harness local** (`plan.py`, a partir do meu `final_score`), **não** pelo
endpoint HTTP — a ponte antiga em `function_app.py` (que só existia no modo hybrid) foi removida.
Portanto o endpoint `/schedule-existing-clips` sozinho ranqueia por tier 1/tier 0 (virality nativo /
duração); tier 2 só aparece quando os clips chegam com `_content_score` do harness.

## Relatório (`/analyze-library`)

`recommended = passou_no_gate_mecânico`. Sem `use_llm`/`llm_scope` (removidos).
`DEFAULT_EXCLUDE_PROJECT_IDS` (`library_report.py`) fixa os projetos de vídeo pessoal que ficam fora
da automação — não remover.

## Env vars JUDGE_* que sobraram

Só quatro ainda têm efeito (as de Foundry/threshold/model/auth foram removidas do código e do
Terraform):

| Env var | Efeito | Default |
|---|---|---|
| `JUDGE_MODE` | `rules_only` (gate) ou `off` (aprova tudo) | `off` (código) / `rules_only` (prod) |
| `JUDGE_INCLUDE_REVIEW_IN_DRY_RUN` | inócuo hoje (não há REVIEW) | `true` |
| `JUDGE_MIN_DURATION_MS` / `JUDGE_MAX_DURATION_MS` | hard rule de duração | 10000 / 180000 |
| `JUDGE_MIN_TEXT_CHARS` | hard rule de tamanho de `title+description` | 10 |

## Validação

```bash
pytest src/tests/test_judge.py src/tests/test_library_report.py -q
python3 tools/curate/prep.py --project-id P3083113Va84   # smoke do harness
```
