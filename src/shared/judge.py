"""Judge determinística para seleção de clips: só regras mecânicas.

A avaliação de SUBSTÂNCIA de conteúdo (payoff/insight) não é mais feita por um LLM
remoto (Azure AI Foundry foi removido) — ela é feita localmente pelo Claude Code via o
harness em ``tools/curate/`` (rubrica única em ``src/shared/curation_rubric.md``), que
alimenta ``_content_score`` nos clips a partir da curadoria. Aqui ficam apenas os gates
determinísticos (duração e tamanho mínimo de texto) usados no caminho de agendamento.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass
class JudgeSettings:
    mode: str
    include_review_in_dry_run: bool
    min_duration_ms: int
    max_duration_ms: int
    min_text_chars: int

    @classmethod
    def from_request(cls, body: dict[str, Any]) -> "JudgeSettings":
        return cls(
            mode=str(body.get("judge_mode", os.environ.get("JUDGE_MODE", "off"))).lower(),
            include_review_in_dry_run=bool(
                body.get(
                    "judge_include_review_in_dry_run",
                    os.environ.get("JUDGE_INCLUDE_REVIEW_IN_DRY_RUN", "true").lower() == "true",
                )
            ),
            min_duration_ms=int(os.environ.get("JUDGE_MIN_DURATION_MS", "10000")),
            max_duration_ms=int(os.environ.get("JUDGE_MAX_DURATION_MS", "180000")),
            min_text_chars=int(os.environ.get("JUDGE_MIN_TEXT_CHARS", "10")),
        )


def judge_clips(clips: list[dict[str, Any]], settings: JudgeSettings) -> list[dict[str, Any]]:
    return [_judge_clip(clip, settings) for clip in clips]


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

    # Qualquer outro modo (off/disabled): aprova sem avaliar (sem LLM remoto).
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
