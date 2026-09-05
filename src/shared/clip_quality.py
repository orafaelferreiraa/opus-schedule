"""
Avaliação de qualidade de cortes para publicação: gate mecânico determinístico.

Regras mecânicas (gate leve): limpeza da fala via transcrição (pausas `__silence`,
repetições imediatas, cortes de palavra `--`, densidade de fillers) + duração.
Os sinais nativos da OpusClip (raw/hook/coherence/connection) são só informativos —
verificado empiricamente que não discriminam qualidade de conteúdo (a própria Opus
é "torcedora": dá nota alta pra qualquer anedota bem contada, mesmo sem substância).

O veredito de SUBSTÂNCIA de conteúdo (payoff/insight) não vive mais aqui: o Azure AI
Foundry (gpt-5-mini) foi removido. A curadoria de conteúdo é feita localmente pelo
Claude Code via o harness em ``tools/curate/`` (rubrica única em
``src/shared/curation_rubric.md``). Este módulo expõe só o gate mecânico, reaproveitado
tanto pelo harness quanto pelo relatório da biblioteca.
"""

from __future__ import annotations

import re
from typing import Any

# Fillers PT-BR (evita estruturais como "que"/"de"/"a"); "cara" é padrão do apresentador.
_FILLERS = {
    "é", "eh", "né", "tipo", "então", "aí", "assim", "tá", "ta",
    "hum", "hmm", "cara", "meio", "tipo assim", "sabe", "beleza",
}
_WORD_RE = re.compile(r"[a-zA-ZÀ-ú]+(?:--)?")

# Gate mecânico (só limpeza de fala + duração). NÃO inclui raw/hook/coherence/connection
# da OpusClip: são informativos apenas, pois não discriminam substância de conteúdo
# (ver docstring do módulo).
#
# `max_pauses_per_min` recalibrado em 2026-08-30: o motor de transcrição da OpusClip
# passou a marcar `__silence` com granularidade muito mais fina (confirmado: 0,7
# marcadores/100 palavras em cortes de fev/2026 vs 10,4/100 palavras em cortes
# reclipados em 30/08/2026 — 15x mais, uniforme entre episódios/convidados diferentes,
# não é característica de fala pior). O valor antigo (6.0) ficava no percentil ~45 da
# distribuição de pausas/min de fev/2026; 13.3 é o valor equivalente no mesmo percentil
# da distribuição de 30/08/2026 (434 cortes) — validado ouvindo/lendo a transcrição de
# cortes perto do novo corte (12/min ainda soa coerente; 25+/min já soa truncado).
DEFAULT_RULES = {
    "max_pauses_per_min": 13.3,
    "max_reps": 2,
    "max_cutoffs": 3,
    "max_filler_pct": 13.0,
    "min_duration_s": 20,
    "max_duration_s": 90,
}


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    return float(v) if isinstance(v, (int, float)) else None


def extract_speech_signals(clip: dict) -> dict:
    """Extrai sinais de limpeza da fala da transcrição do corte."""
    text = str(clip.get("text", "") or "")
    pauses = text.count("__silence")
    words = _WORD_RE.findall(text.replace("__silence", " ").lower())
    cutoffs = sum(1 for w in words if w.endswith("--"))
    base = [w for w in words if not w.endswith("--")]
    reps = sum(1 for i in range(1, len(base)) if base[i] == base[i - 1] and len(base[i]) > 1)
    fillers = sum(1 for w in base if w in _FILLERS)
    n = max(1, len(base))
    dur_s = int((clip.get("durationMs", 0) or 0) / 1000)
    return {
        "duration_s": dur_s,
        "words": len(base),
        "wpm": round(len(base) / (dur_s / 60), 0) if dur_s else 0,
        "pauses_per_min": round(pauses / (dur_s / 60), 1) if dur_s else 0.0,
        "reps": reps,
        "cutoffs": cutoffs,
        "filler_pct": round(100 * fillers / n, 1),
    }


def rule_verdict(clip: dict, signals: dict, rules: dict | None = None) -> dict:
    """Aplica o gate mecânico (limpeza de fala + duração). Retorna {passed, reasons}."""
    r = {**DEFAULT_RULES, **(rules or {})}
    reasons: list[str] = []

    if signals["pauses_per_min"] > r["max_pauses_per_min"]:
        reasons.append(f"pausas {signals['pauses_per_min']}/min>{r['max_pauses_per_min']}")
    if signals["reps"] > r["max_reps"]:
        reasons.append(f"repetições {signals['reps']}>{r['max_reps']}")
    if signals["cutoffs"] > r["max_cutoffs"]:
        reasons.append(f"gaguejo {signals['cutoffs']}>{r['max_cutoffs']}")
    if signals["filler_pct"] > r["max_filler_pct"]:
        reasons.append(f"filler {signals['filler_pct']}%>{r['max_filler_pct']}%")
    d = signals["duration_s"]
    if d and not (r["min_duration_s"] <= d <= r["max_duration_s"]):
        reasons.append(f"duração {d}s fora {r['min_duration_s']}-{r['max_duration_s']}s")

    return {"passed": not reasons, "reasons": reasons}
