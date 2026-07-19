"""
Avaliação de qualidade de cortes para publicação.

Combina duas camadas:
1. Regras mecânicas (gate leve): limpeza da fala via transcrição (pausas `__silence`,
   repetições imediatas, cortes de palavra `--`, densidade de fillers) + duração.
   Os sinais nativos da OpusClip (raw/hook/coherence/connection) são só informativos —
   verificado empiricamente que não discriminam qualidade de conteúdo (a própria Opus
   é "torcedora": dá nota alta pra qualquer anedota bem contada, mesmo sem substância).
2. Veredito de CONTEÚDO do LLM gpt-5-mini: julga se o corte tem substância/payoff real
   para o público do LowOpsCast (insight técnico, conselho de carreira, humor genuíno,
   curiosidade, virada surpreendente) — não apenas "fala limpa e coerente".

recommended = passou no gate mecânico E o LLM aprovou o conteúdo.
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

# Gate mecânico (só limpeza de fala + duração — calibrado na distribuição real de
# 344 cortes). NÃO inclui raw/hook/coherence/connection da OpusClip: são informativos
# apenas, pois não discriminam substância de conteúdo (ver docstring do módulo).
DEFAULT_RULES = {
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


# ---------------------------------------------------------------------------
# LLM gpt-5-mini (veredito holístico sobre a transcrição)
# ---------------------------------------------------------------------------

_LLM_SYSTEM = (
    "Você é um curador CRÍTICO e exigente de cortes virais para o LowOpsCast, um podcast "
    "de tecnologia/DevOps brasileiro. Público: profissionais de TI, 25-34 anos, majoritariamente "
    "homens, BR. Cortes que funcionam trazem PELO MENOS UM destes payoffs concretos: "
    "(1) insight técnico específico e útil; (2) conselho de carreira acionável (ex: certificações, "
    "como entrar na área, ATS, mudança de carreira); (3) humor genuíno sobre a rotina de TI/DevOps "
    "(ex: 'deploy sexta 17h59', crise de produção); (4) fato surpreendente ou curiosidade regional "
    "(ex: Pomerode, Floripa, comparação Brasil x exterior); (5) uma virada de história genuinamente "
    "inesperada com uma LIÇÃO clara e explícita no final.\n\n"
    "REJEITE (approve=false) sempre que o corte for: uma anedota pessoal genérica sem lição/insight "
    "claro (ex: 'quando eu era criança eu gostava de computador e um tio me deu o dele'); uma "
    "história sem virada nem payoff; conteúdo raso que não ensina, não surpreende e não diverte "
    "nada específico; ou que só faz sentido com contexto externo que o corte não dá.\n\n"
    "IMPORTANTE: 'a fala flui bem e é coerente' NÃO é critério de aprovação — isso é só qualidade "
    "de edição. O approve deve refletir EXCLUSIVAMENTE se o CONTEÚDO tem substância suficiente para "
    "fazer um estranho parar de rolar o feed e sentir que valeu o tempo assistido. Seja rigoroso: "
    "quando em dúvida, reprove. Ignore qualidade de fala (pausas/repetições/fillers) na decisão de "
    "approve — isso entra só em speech_flags, como nota de polimento.\n\n"
    "Responda SOMENTE JSON com as chaves: final_score (0-100 int, baseado na força do CONTEÚDO), "
    "approve (bool, o conteúdo tem substância/payoff real), "
    "content_flags (array com zero ou mais de: 'sem_payoff','generico','anedota_fraca',"
    "'fora_do_tema','previsivel','sem_insight','gancho_fraco','incompleto'), "
    "speech_flags (array com zero ou mais de: 'repeticao','pausas','filler','gaguejo'), "
    "reason (frase curta em PT-BR explicando o approve com foco em CONTEÚDO)."
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
    """Chama o gpt-5-mini para julgar SUBSTÂNCIA DE CONTEÚDO do corte.

    Retorna {ok, score, approve, content_flags, speech_flags, reason}. `approve`
    reflete só o conteúdo (payoff/insight/humor/curiosidade) — qualidade de fala
    fica em `speech_flags` como nota de polimento, não afeta approve.
    """
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
            "content_flags": [str(f) for f in (data.get("content_flags") or [])],
            "speech_flags": [str(f) for f in (data.get("speech_flags") or [])],
            "reason": str(data.get("reason", ""))[:280],
        }
    except Exception as exc:  # noqa: BLE001 - falha do LLM não derruba o relatório
        return {
            "ok": False,
            "score": None,
            "approve": None,
            "content_flags": [],
            "speech_flags": [],
            "reason": f"llm_error: {type(exc).__name__}",
        }
