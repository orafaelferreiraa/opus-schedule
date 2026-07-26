---
name: clip-curation-internals
description: Mecânica interna da curadoria de cortes — as DUAS implementações de LLM (shared/judge.py no caminho de agendamento e shared/clip_quality.py no caminho de relatório) que leem os mesmos env vars JUDGE_* com defaults, contratos JSON e concorrência diferentes, além dos gates mecânicos e das faixas de decisão. Use ao mexer em judge.py, clip_quality.py, library_report.py, no prompt/rubrica de curadoria, em qualquer env var JUDGE_*, ao ligar ou depurar o modo hybrid, e quando o usuário falar de judge, curadoria, aprovar/reprovar corte, threshold, score de conteúdo ou gpt-5-mini.
---

# Mecânica da curadoria

`distribution-strategy` cobre a política editorial (o que viraliza, cadência, ordem dos tiers, CTA).
Esta skill cobre a **mecânica**: quem chama o LLM, com que parâmetros e o que quebra em silêncio.

## O fato central: existem DUAS implementações de LLM, não uma

Elas leem os **mesmos** env vars `JUDGE_*` mas são código independente, com defaults e contratos
diferentes. Nunca foram reconciliadas.

| | `shared/judge.py` | `shared/clip_quality.py` |
|---|---|---|
| Caminho | `POST /schedule-existing-clips` | `POST /analyze-library` |
| Param de token | **`max_tokens: 300`** hardcoded (`judge.py:248`) | **`max_completion_tokens`**, default 1500 (`:134`) |
| Contrato JSON | `final_score` · `soft_signals` · `audit_reason` | `final_score` · `approve` · `content_flags` · `speech_flags` · `reason` |
| Duração aceita | 10 s – 180 s | 20 s – 90 s (`DEFAULT_RULES`) |
| Concorrência | **loop serial** (`judge.py:73-77`) | `ThreadPoolExecutor(max_workers=10)` (`library_report.py:100`) |
| Falha do LLM | → `REVIEW`, `source="fallback"` | → `ok=False` → não recomendado |

**A armadilha nº 1 deste subsistema:** os dois arquivos carregam a **mesma rubrica editorial**
("só vale postar se tiver payoff concreto; fala limpa NÃO basta") escrita com palavras e chaves JSON
diferentes — `judge.py:252-263` e `clip_quality.py:100-124`. Pedido de "deixar o judge mais
rigoroso" ou "ajustar a rubrica" **precisa tocar os dois**. Editar um só faz a política divergir
entre os dois endpoints sem nenhum sinal de erro.

Matriz completa de env var × default de cada arquivo × valor do Terraform × sobrescrevível no body:
[reference/judge-config.md](reference/judge-config.md).

## Modos e o gate que desliga tudo em silêncio

`function_app.py:254` liga a curadoria com `if judge_settings.mode in {"rules_only", "hybrid"}`.

Qualquer outro valor — `"on"`, `"llm"`, `"hibrido"`, `"Hybrid"` com maiúscula já é tratado por
`.lower()`, mas um typo não — **pula o bloco inteiro e agenda todos os clips**. Não há log, não há
erro, não há métrica. O branch `source="disabled"` em `judge.py:141-152` é inalcançável via HTTP.
Se a curadoria "não está filtrando nada", conferir o valor exato de `JUDGE_MODE` é o primeiro passo.

- `off` — não usado pelo HTTP (o gate acima já exclui).
- `rules_only` — **é o modo de produção hoje** (`main.tf:109`). Só regras mecânicas; devolve
  `final_score` uniforme **100**, que é deliberadamente ignorado pelo ranking.
- `hybrid` — chama o LLM. Ver a seção de risco abaixo antes de ligar.

## Três faixas de decisão, não um corte

`judge.py:184-190`, com `threshold` default 70:

| Faixa | Decisão |
|---|---|
| `score >= threshold` | `APPROVE` |
| `threshold-10 < score < threshold` | `REVIEW` (faixa de 9 pontos) |
| `score <= threshold-10` | `REJECT` |

Subir o threshold para 80 **também** move o piso de rejeição para 70. Não existe knob separado para
a largura da faixa.

E o que é feito com `REVIEW` depende do dry-run (`function_app.py:281-284`):

```
dry_run E include_review_in_dry_run  → aceita {APPROVE, REVIEW}
qualquer outro caso                  → aceita só {APPROVE}
```

Em produção `JUDGE_INCLUDE_REVIEW_IN_DRY_RUN="true"` (`main.tf:117`).

## Risco ao ligar o modo hybrid — verificar antes de acreditar

Três fatos verificados que se combinam mal:

1. `judge.py:248` manda `"max_tokens": 300`. Deployments de raciocínio da família GPT-5 tipicamente
   **rejeitam** `max_tokens` (400 `unsupported_parameter`) e exigem `max_completion_tokens` — que é
   exatamente o que o `clip_quality.py` usa. Existe até um env var `JUDGE_MAX_COMPLETION_TOKENS`,
   **não ligado** a esta chamada.
2. `judge_primary_model` **e** `judge_fallback_model` são ambos `gpt-5-mini`
   (`variables.tf:88-99`). A escada primário → fallback (`judge.py:154-182`) não resgata um erro de
   parâmetro: o fallback falha igual.
3. Toda falha do LLM cai em `REVIEW`/`source="fallback"`. Com `include_review_in_dry_run=true`, um
   `dry_run` **parece perfeito** (aceita REVIEW) e a execução real agenda **zero clips** (só APROVE).

Nenhum teste cobre o corpo HTTP do hybrid — `test_judge.py` só exercita `_safe_json`,
`_run_hard_rules` e `_build_auth_headers`.

**Portanto:** antes de declarar que hybrid funciona, fazer **uma** chamada real (curl ou um clip só)
e conferir que voltou `source="llm"`, não `source="fallback"`. Não confiar em dry-run verde.

## Retry: mais amplo do que o rótulo sugere

`judge.py:284` classifica 408/429/5xx como transiente, mas o `except Exception` de `judge.py:292`
faz retry de **tudo** — 401, erro de parse de JSON, endpoint errado. Com `max_retries=2` (3
tentativas) × 2 deployments × até 12 s, **em série**, uma coleção grande em hybrid estoura o timeout
da Function. O caminho de relatório é paralelo; o de agendamento **não é**.

## Gates mecânicos: os dois medem coisas diferentes

**`judge.py:_run_hard_rules`** (`:205-219`) — o texto que ele mede é `title + description`,
**não a transcrição**. Mas o prompt enviado ao LLM usa `clip["text"]` (a transcrição, `:236`).
Consequência: um corte com transcrição rica e metadados vazios é **hard-rejected por
`text_too_short` antes do LLM ver qualquer coisa**.

**`clip_quality.extract_speech_signals`** (`:52-70`) — mede a transcrição de verdade:
`__silence` conta pausas, sufixo `--` conta cortes de palavra, repetição imediata, densidade de
filler. `DEFAULT_RULES` foi **calibrado na distribuição real de 344 cortes** (`:36-45`); não mexer
nos números sem redistribuir.

A lista `_FILLERS` é **PT-BR e específica do apresentador** — `"cara"` está lá porque é tique dele
(`:29-32`). Adicionar filler em inglês ou trocar por tokenizer genérico produz sinais todos zerados,
que passam por qualquer gate.

## Anti-padrão documentado: os scores nativos da OpusClip

`raw` / `hook` / `coherence` / `connection` são reportados mas **excluídos de propósito de todo
gate** (`clip_quality.py:1-16` e `:36-37`). Motivo verificado empiricamente: a própria OpusClip é
"torcedora" — dá nota alta para qualquer anedota bem contada, mesmo sem substância.

Quem for "melhorar o gate" vai querer usar esses campos primeiro. É justamente o que não se faz.
`test_library_report.py:73-82` trava esse comportamento.

## A ponte para o ranking só existe em hybrid

`function_app.py:291-299` anexa `_content_score` ao dict do clip **apenas** para
`source == "llm"` — ou seja, só em hybrid. É mutação de dict em chave privada, consumida por
`_CONTENT_FIELDS` em `schedule_matrix._clip_score` (tier 2).

`rules_only` devolve 100 uniforme e é **deliberadamente excluído** da ponte: um score constante não
ordena nada. Então em produção hoje o ranking opera em tier 1/tier 0, nunca em tier 2.

## Knob morto: `JUDGE_PROVIDER`

Definido em `main.tf:110` como `"foundry"`, lido para `settings.provider` em `judge.py:48`, e
**nunca usado em lugar algum**. `_call_foundry_judge` é chamado incondicionalmente. Não é um ponto de
extensão funcional — mudar seu valor não faz nada.

## Relatório (`/analyze-library`)

`recommended = passou_no_gate_mecânico AND llm.approve`. `llm_scope` aceita `candidates` (só quem
passou no gate) ou `all`. `DEFAULT_EXCLUDE_PROJECT_IDS` (`library_report.py:29`) fixa três projetos
de vídeo pessoal que devem ficar fora da automação — não remover.

`LLMSettings.enabled` exige `JUDGE_AZURE_OPENAI_ENDPOINT` presente (`clip_quality.py:138-139`);
sem ele, `use_llm=true` **silenciosamente não faz nada**.

## Validação

```bash
pytest src/tests/test_judge.py src/tests/test_library_report.py -q
```

Lembrar da cobertura real: nenhum teste toca o corpo HTTP do hybrid.
