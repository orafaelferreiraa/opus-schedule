"""
Relatório de qualidade da biblioteca de cortes (OpusClip).

Enumera os projetos, lê os cortes e avalia quais valem postar usando os sinais
NATIVOS da OpusClip — `score` (0-100) e `judgeResult` (hookScore/hookComment) —
mais regras simples de duração. Não usa LLM e independe do layout (que a API não
expõe de forma confiável). O mesmo código roda local ou dentro do Function App.
"""

from __future__ import annotations

from typing import Any

# Projetos que são vídeos pessoais do Rafael — fora da automação (ver memória).
DEFAULT_EXCLUDE_PROJECT_IDS = {"P30318211wd3", "P3020416EqOU", "P3020716CxZv"}


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _assess_clip(
    clip: dict,
    *,
    min_score: float,
    min_hook: float,
    min_dur_s: int,
    max_dur_s: int,
) -> dict:
    full_id = str(clip.get("id", ""))
    judge = clip.get("judgeResult") or {}
    score = _num(clip.get("score"))
    if score is None:
        score = _num(judge.get("curvedScore"))
    hook = _num(judge.get("hookScore"))
    dur_s = int(round((clip.get("durationMs", 0) or 0) / 1000))

    reasons: list[str] = []
    recommended = True
    if score is None or score < min_score:
        recommended = False
        reasons.append(f"score {score if score is not None else '—'} < {min_score:g}")
    if hook is not None and hook < min_hook:
        recommended = False
        reasons.append(f"hook {hook:g} < {min_hook:g}")
    if dur_s and not (min_dur_s <= dur_s <= max_dur_s):
        recommended = False
        reasons.append(f"duração {dur_s}s fora de {min_dur_s}-{max_dur_s}s")

    return {
        "id": full_id,
        "title": str(clip.get("title", ""))[:100],
        "duration_s": dur_s,
        "score": score,
        "hook_score": hook,
        "hook_comment": str(judge.get("hookComment", ""))[:280],
        "recommended": recommended,
        "reasons": reasons,
    }


def build_library_report(
    client,
    *,
    project_ids: list[str] | None = None,
    exclude_project_ids: set[str] | list[str] | None = None,
    min_score: float = 85,
    min_hook: float = 6,
    min_dur_s: int = 15,
    max_dur_s: int = 100,
    top_n_per_project: int | None = None,
) -> dict:
    """Monta o relatório de qualidade. `client` é um OpusClient (ou compatível)."""
    exclude = set(
        exclude_project_ids
        if exclude_project_ids is not None
        else DEFAULT_EXCLUDE_PROJECT_IDS
    )

    if project_ids:
        projects = [{"projectId": pid} for pid in project_ids]
    else:
        projects = client.list_projects()

    projects_out: list[dict] = []
    all_clips: list[dict] = []
    excluded: list[str] = []
    analyzed = 0

    for proj in projects:
        pid = str(proj.get("projectId") or proj.get("id") or "")
        if not pid:
            continue
        if pid in exclude:
            excluded.append(pid)
            continue
        title = str((proj.get("sourceInfo") or {}).get("title") or proj.get("title") or "")
        clips = client.get_clips_by_project(pid)
        assessed = [
            _assess_clip(c, min_score=min_score, min_hook=min_hook, min_dur_s=min_dur_s, max_dur_s=max_dur_s)
            for c in clips
            if isinstance(c, dict)
        ]
        assessed.sort(key=lambda a: (a["score"] if a["score"] is not None else -1), reverse=True)
        for a in assessed:
            a["projectId"] = pid
            a["projectTitle"] = title
            all_clips.append(a)
        analyzed += 1
        projects_out.append(
            {
                "projectId": pid,
                "title": title,
                "total_clips": len(assessed),
                "recommended": sum(1 for a in assessed if a["recommended"]),
                "clips": assessed[:top_n_per_project] if top_n_per_project else assessed,
            }
        )

    all_clips.sort(key=lambda a: (a["score"] if a["score"] is not None else -1), reverse=True)
    return {
        "criteria": {
            "min_score": min_score,
            "min_hook": min_hook,
            "duration_s": [min_dur_s, max_dur_s],
        },
        "projects_analyzed": analyzed,
        "excluded_projects": excluded,
        "total_clips": len(all_clips),
        "recommended_total": sum(1 for a in all_clips if a["recommended"]),
        "projects": projects_out,
    }
