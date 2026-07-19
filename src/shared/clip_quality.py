"""
Avaliação de qualidade de cortes para publicação.

Combina três camadas:
1. Sinais nativos da OpusClip (judgeResult: raw score, hook, coherence, connection).
2. Limpeza da fala derivada da transcrição (pausas `__silence`, repetições imediatas,
   cortes de palavra `--`, densidade de fillers) — o que o usuário pediu.
3. Regras rigorosas determinísticas (gate) + veredito opcional do LLM gpt-5-mini.

Sem dependência de layout (que a API não expõe de forma confiável).
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import httpx

# Fillers PT-BR (evita estruturais como "que"/"de"/"a"); "cara" é padrão do apresentador.
_FILLERS = {
    "é", "eh", "né", "tipo", "então", "aí", "assim", "tá", "ta",
    "hum", "hmm", "cara", "meio", "tipo assim", "sabe", "beleza",
}
_WORD_RE = re.compile(r"[a-zA-ZÀ-ú]+(?:--)?")

# Limiares rigorosos (calibrados na distribuição real de 344 cortes).
DEFAULT_RULES = {
    "min_raw": 35,
    "min_hook": 9,
    "min_coherence": 9,
    "min_connection": 8,
    "max_pauses_per_min": 6.0,
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
    """Aplica as regras rigorosas. Retorna {passed, reasons}."""
    r = {**DEFAULT_RULES, **(rules or {})}
    jr = clip.get("judgeResult") or {}
    raw = _num(jr.get("score"))
    hook = _num(jr.get("hookScore"))
    coh = _num(jr.get("coherenceScore"))
    conn = _num(jr.get("connectionScore"))
    reasons: list[str] = []

    if raw is None or raw < r["min_raw"]:
        reasons.append(f"raw {raw if raw is not None else '—'}<{r['min_raw']}")
    if hook is None or hook < r["min_hook"]:
        reasons.append(f"hook {hook if hook is not None else '—'}<{r['min_hook']}")
    if coh is None or coh < r["min_coherence"]:
        reasons.append(f"coerência {coh if coh is not None else '—'}<{r['min_coherence']}")
    if conn is None or conn < r["min_connection"]:
        reasons.append(f"conexão {conn if conn is not None else '—'}<{r['min_connection']}")
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


# ---------------------------------------------------------------------------
# LLM gpt-5-mini (veredito holístico sobre a transcrição)
# ---------------------------------------------------------------------------

_LLM_SYSTEM = (
    "Você é um curador de cortes de podcast de tecnologia/DevOps (PT-BR) para YouTube "
    "Shorts e TikTok. Julgue se o corte está BOM PARA POSTAR como está. Penalize: "
    "palavras repetidas/gaguejo, muitas pausas, excesso de fillers (tipo, né, cara), "
    "gancho fraco, ideia incompleta ou que não faz sentido sozinha. "
    "Responda SOMENTE JSON com as chaves: final_score (0-100 int), approve (bool), "
    "flags (array com zero ou mais de: 'repeticao','pausas','filler','gancho_fraco',"
    "'incoerente','incompleto'), reason (frase curta em PT-BR)."
)


class LLMSettings:
    def __init__(self) -> None:
        self.endpoint = os.environ.get("JUDGE_AZURE_OPENAI_ENDPOINT", "").rstrip("/")
        self.deployment = os.environ.get("JUDGE_MODEL_DEPLOYMENT_PRIMARY", "gpt-5-mini")
        self.api_version = os.environ.get("JUDGE_API_VERSION", "2024-12-01-preview")
        self.auth_mode = os.environ.get("JUDGE_AUTH_MODE", "managed_identity")
        self.api_key = os.environ.get("JUDGE_AZURE_OPENAI_API_KEY", "")
        self.max_completion_tokens = int(os.environ.get("JUDGE_MAX_COMPLETION_TOKENS", "1500"))
        self.timeout_s = float(os.environ.get("JUDGE_TIMEOUT_MS", "30000")) / 1000.0

    @property
    def enabled(self) -> bool:
        return bool(self.endpoint)

    def headers(self) -> dict:
        if self.auth_mode == "api_key":
            if not self.api_key:
                raise RuntimeError("JUDGE_AZURE_OPENAI_API_KEY ausente para auth_mode=api_key")
            return {"api-key": self.api_key, "Content-Type": "application/json"}
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider

        provider = get_bearer_token_provider(
            DefaultAzureCredential(exclude_interactive_browser_credential=True),
            "https://cognitiveservices.azure.com/.default",
        )
        return {"Authorization": f"Bearer {provider()}", "Content-Type": "application/json"}


def llm_assess(clip: dict, settings: LLMSettings) -> dict:
    """Chama o gpt-5-mini para julgar o corte. Retorna {score, approve, flags, reason, ok}."""
    title = str(clip.get("title", "") or "")
    transcript = str(clip.get("text", "") or "").replace("__silence", " [pausa] ")[:4000]
    body = {
        "messages": [
            {"role": "system", "content": _LLM_SYSTEM},
            {"role": "user", "content": f"titulo: {title}\ntranscricao: {transcript}"},
        ],
        "max_completion_tokens": settings.max_completion_tokens,
        "response_format": {"type": "json_object"},
    }
    url = f"{settings.endpoint}/openai/deployments/{settings.deployment}/chat/completions?api-version={settings.api_version}"
    try:
        with httpx.Client(timeout=settings.timeout_s) as client:
            resp = client.post(url, headers=settings.headers(), json=body)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
        return {
            "ok": True,
            "score": int(data.get("final_score", 0)),
            "approve": bool(data.get("approve", False)),
            "flags": [str(f) for f in (data.get("flags") or [])],
            "reason": str(data.get("reason", ""))[:280],
        }
    except Exception as exc:  # noqa: BLE001 - falha do LLM não derruba o relatório
        return {"ok": False, "score": None, "approve": None, "flags": [], "reason": f"llm_error: {type(exc).__name__}"}
