"""
Judge hibrida para selecao de clips: regras deterministicas + avaliacao LLM.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

from shared.telemetry import attrs, logger


@dataclass
class JudgeSettings:
    mode: str
    threshold: int
    include_review_in_dry_run: bool
    provider: str
    endpoint: str
    api_key: str
    api_version: str
    model_deployment_primary: str
    model_deployment_fallback: str
    timeout_ms: int
    max_retries: int
    min_duration_ms: int
    max_duration_ms: int
    min_text_chars: int

    @classmethod
    def from_request(cls, body: dict[str, Any]) -> "JudgeSettings":
        return cls(
            mode=str(body.get("judge_mode", os.environ.get("JUDGE_MODE", "off"))).lower(),
            threshold=int(body.get("judge_threshold", os.environ.get("JUDGE_THRESHOLD", "70"))),
            include_review_in_dry_run=bool(
                body.get(
                    "judge_include_review_in_dry_run",
                    os.environ.get("JUDGE_INCLUDE_REVIEW_IN_DRY_RUN", "true").lower() == "true",
                )
            ),
            provider=str(os.environ.get("JUDGE_PROVIDER", "foundry")).lower(),
            endpoint=str(os.environ.get("JUDGE_AZURE_OPENAI_ENDPOINT", "")).rstrip("/"),
            api_key=str(os.environ.get("JUDGE_AZURE_OPENAI_API_KEY", "")),
            api_version=str(os.environ.get("JUDGE_API_VERSION", "2025-01-01-preview")),
            model_deployment_primary=str(
                body.get(
                    "judge_model_deployment_primary",
                    os.environ.get("JUDGE_MODEL_DEPLOYMENT_PRIMARY", "gpt-5.6-sol"),
                )
            ),
            model_deployment_fallback=str(
                body.get(
                    "judge_model_deployment_fallback",
                    os.environ.get("JUDGE_MODEL_DEPLOYMENT_FALLBACK", "gpt-5.4-mini"),
                )
            ),
            timeout_ms=int(os.environ.get("JUDGE_TIMEOUT_MS", "12000")),
            max_retries=int(os.environ.get("JUDGE_MAX_RETRIES", "2")),
            min_duration_ms=int(os.environ.get("JUDGE_MIN_DURATION_MS", "10000")),
            max_duration_ms=int(os.environ.get("JUDGE_MAX_DURATION_MS", "180000")),
            min_text_chars=int(os.environ.get("JUDGE_MIN_TEXT_CHARS", "10")),
        )


def judge_clips(clips: list[dict[str, Any]], settings: JudgeSettings) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for clip in clips:
        results.append(_judge_clip(clip, settings))
    return results


def summarize_judge(results: list[dict[str, Any]]) -> dict[str, Any]:
    summary = {
        "total": len(results),
        "approved": 0,
        "review": 0,
        "rejected": 0,
        "source_rules_only": 0,
        "source_llm": 0,
        "source_fallback": 0,
    }
    for result in results:
        decision = result.get("decision")
        source = str(result.get("source", ""))
        if decision == "APPROVE":
            summary["approved"] += 1
        elif decision == "REVIEW":
            summary["review"] += 1
        else:
            summary["rejected"] += 1

        if source == "rules_only":
            summary["source_rules_only"] += 1
        elif source == "llm":
            summary["source_llm"] += 1
        elif source == "fallback":
            summary["source_fallback"] += 1
    return summary


def _judge_clip(clip: dict[str, Any], settings: JudgeSettings) -> dict[str, Any]:
    full_id = str(clip.get("id", ""))
    clip_short_id = full_id.split(".", 1)[1] if "." in full_id else full_id
    project_id = str(clip.get("projectId", ""))

    hard_fail_reasons = _run_hard_rules(clip, settings)
    if hard_fail_reasons:
        return {
            "id": full_id,
            "clip_id": clip_short_id,
            "project_id": project_id,
            "decision": "REJECT",
            "final_score": 0,
            "hard_fail_reasons": hard_fail_reasons,
            "soft_signals": {},
            "audit_reason": "Falha em regras deterministicas",
            "source": "rules_only",
        }

    if settings.mode == "rules_only":
        return {
            "id": full_id,
            "clip_id": clip_short_id,
            "project_id": project_id,
            "decision": "APPROVE",
            "final_score": 100,
            "hard_fail_reasons": [],
            "soft_signals": {"rules": 100},
            "audit_reason": "Aprovado por regras deterministicas",
            "source": "rules_only",
        }

    if settings.mode != "hybrid":
        return {
            "id": full_id,
            "clip_id": clip_short_id,
            "project_id": project_id,
            "decision": "APPROVE",
            "final_score": 100,
            "hard_fail_reasons": [],
            "soft_signals": {},
            "audit_reason": "Judge desativada",
            "source": "disabled",
        }

    try:
        llm_result = _call_foundry_judge(clip, settings, settings.model_deployment_primary)
    except Exception as first_exc:
        logger.warning(
            "Judge primary falhou, tentando fallback",
            extra={
                "custom_dimensions": attrs(
                    lowopscast_judge_clip_id=clip_short_id,
                    lowopscast_judge_primary=settings.model_deployment_primary,
                    lowopscast_judge_fallback=settings.model_deployment_fallback,
                    lowopscast_judge_error=str(first_exc),
                )
            },
        )
        try:
            llm_result = _call_foundry_judge(clip, settings, settings.model_deployment_fallback)
            llm_result["source"] = "llm"
        except Exception:
            return {
                "id": full_id,
                "clip_id": clip_short_id,
                "project_id": project_id,
                "decision": "REVIEW",
                "final_score": 50,
                "hard_fail_reasons": [],
                "soft_signals": {},
                "audit_reason": "LLM indisponivel, fallback para revisao manual",
                "source": "fallback",
            }

    score = int(max(0, min(100, int(llm_result.get("final_score", 0)))))
    if score >= settings.threshold:
        decision = "APPROVE"
    elif score <= max(0, settings.threshold - 10):
        decision = "REJECT"
    else:
        decision = "REVIEW"

    return {
        "id": full_id,
        "clip_id": clip_short_id,
        "project_id": project_id,
        "decision": decision,
        "final_score": score,
        "hard_fail_reasons": [],
        "soft_signals": llm_result.get("soft_signals", {}),
        "audit_reason": llm_result.get("audit_reason", ""),
        "source": llm_result.get("source", "llm"),
    }


def _run_hard_rules(clip: dict[str, Any], settings: JudgeSettings) -> list[str]:
    reasons: list[str] = []
    duration = int(clip.get("durationMs", 0) or 0)
    text = " ".join(
        [
            str(clip.get("title", "") or "").strip(),
            str(clip.get("description", "") or "").strip(),
        ]
    ).strip()

    if duration and duration < settings.min_duration_ms:
        reasons.append("duration_too_short")
    if duration and duration > settings.max_duration_ms:
        reasons.append("duration_too_long")
    if len(text) < settings.min_text_chars:
        reasons.append("text_too_short")
    return reasons


def _call_foundry_judge(clip: dict[str, Any], settings: JudgeSettings, deployment: str) -> dict[str, Any]:
    if not settings.endpoint or not settings.api_key:
        raise RuntimeError("JUDGE_AZURE_OPENAI_ENDPOINT/JUDGE_AZURE_OPENAI_API_KEY ausentes")

    url = (
        f"{settings.endpoint}/openai/deployments/{deployment}/chat/completions"
        f"?api-version={settings.api_version}"
    )

    prompt_clip = {
        "id": str(clip.get("id", "")),
        "title": str(clip.get("title", "") or ""),
        "description": str(clip.get("description", "") or ""),
        "hashtags": str(clip.get("hashtags", "") or ""),
        "duration_ms": int(clip.get("durationMs", 0) or 0),
    }

    body = {
        "response_format": {"type": "json_object"},
        "max_tokens": 300,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a strict short-video quality judge. "
                    "Return only valid JSON with keys: final_score, soft_signals, audit_reason. "
                    "final_score is 0-100 integer. soft_signals is an object with rhythm, clarity, context, engagement, pauses (0-100)."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Evaluate this clip for publish-readiness. "
                    "Prefer penalizing incoherent cuts, weak context, and long pauses.\n"
                    f"clip={json.dumps(prompt_clip, ensure_ascii=True)}"
                ),
            },
        ],
    }

    headers = {"api-key": settings.api_key, "Content-Type": "application/json"}
    timeout_s = max(1.0, settings.timeout_ms / 1000.0)

    attempts = max(1, settings.max_retries + 1)
    for attempt in range(attempts):
        started = time.perf_counter()
        try:
            with httpx.Client(timeout=timeout_s) as client:
                resp = client.post(url, headers=headers, json=body)
            if resp.status_code in (408, 429) or resp.status_code >= 500:
                raise RuntimeError(f"transient_status_{resp.status_code}")
            resp.raise_for_status()
            payload = resp.json()
            content = payload["choices"][0]["message"]["content"]
            parsed = _safe_json(content)
            parsed["source"] = "llm"
            return parsed
        except Exception:
            if attempt + 1 >= attempts:
                raise
            # backoff curto para nao aumentar muito a latencia da function
            time.sleep(0.35 * (attempt + 1))
        finally:
            _ = round((time.perf_counter() - started) * 1000, 2)

    raise RuntimeError("judge_llm_unreachable")


def _safe_json(content: str) -> dict[str, Any]:
    data = json.loads(content)
    return {
        "final_score": int(data.get("final_score", 0)),
        "soft_signals": data.get("soft_signals", {}) if isinstance(data.get("soft_signals", {}), dict) else {},
        "audit_reason": str(data.get("audit_reason", "")),
    }
