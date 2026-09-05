"""
Relatório de qualidade da biblioteca de cortes (OpusClip): gate mecânico.

Enumera os projetos, lê os cortes e aplica o gate mecânico determinístico (limpeza da
fala da transcrição — pausas, repetições, gaguejo, filler — + duração). `recommended` =
passou no gate mecânico.

A avaliação de SUBSTÂNCIA de conteúdo (payoff/insight) foi removida deste caminho junto
com o Azure AI Foundry: a curadoria de conteúdo é feita localmente pelo Claude Code via o
harness em ``tools/curate/`` (rubrica única em ``src/shared/curation_rubric.md``).

Sinais nativos da OpusClip (raw/hook/coherence/connection) são só informativos — não
discriminam substância (verificado empiricamente: anedotas fracas recebem nota alta).
Independe do layout. O mesmo código roda local ou dentro do Function App.
"""

from __future__ import annotations

from shared.clip_quality import (
    DEFAULT_RULES,
    _num,
    extract_speech_signals,
    rule_verdict,
)

# Projetos que são vídeos pessoais do Rafael — fora da automação (ver memória).
DEFAULT_EXCLUDE_PROJECT_IDS = {
    "P30318211wd3",  # comunicação2.mp4
    "P3020416EqOU",  # 20260203_193915.mp4
    "P3020716CxZv",  # 1.mp4
    "P30830225X8I",  # 20260723_141414.mp4
    "P3020412QRU9",  # Tech Floripa Cast #010 - Rafael Ferreira (outro show, não é LowOpsCast)
    "P3083021EbE1",  # Cloud para Devs – Do Localhost ao Deploy Escalável
}


def _assess(clip: dict, rules: dict | None) -> dict:
    signals = extract_speech_signals(clip)
    rule = rule_verdict(clip, signals, rules)
    jr = clip.get("judgeResult") or {}
    return {
        "id": str(clip.get("id", "")),
        "title": str(clip.get("title", ""))[:100],
        "duration_s": signals["duration_s"],
        "raw": _num(jr.get("score")),
        "hook": _num(jr.get("hookScore")),
        "coherence": _num(jr.get("coherenceScore")),
        "connection": _num(jr.get("connectionScore")),
        "pauses_per_min": signals["pauses_per_min"],
        "reps": signals["reps"],
        "cutoffs": signals["cutoffs"],
        "filler_pct": signals["filler_pct"],
        "rule_passed": rule["passed"],
        "rule_reasons": rule["reasons"],
    }


def build_library_report(
    client,
    *,
    project_ids: list[str] | None = None,
    exclude_project_ids: set[str] | list[str] | None = None,
    rules: dict | None = None,
    top_n_per_project: int | None = None,
) -> dict:
    """Monta o relatório de qualidade (gate mecânico). `client` é um OpusClient (ou compatível)."""
    exclude = set(exclude_project_ids if exclude_project_ids is not None else DEFAULT_EXCLUDE_PROJECT_IDS)
    projects = [{"projectId": pid} for pid in project_ids] if project_ids else client.list_projects()

    projects_out: list[dict] = []
    all_assessments: list[dict] = []
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
        assessed = [_assess(c, rules) for c in client.get_clips_by_project(pid) if isinstance(c, dict)]
        for a in assessed:
            a["projectId"] = pid
            a["projectTitle"] = title
        all_assessments.extend(assessed)
        analyzed += 1
        projects_out.append({"projectId": pid, "title": title, "_assessed": assessed})

    # Decisão final: passou no gate mecânico.
    for a in all_assessments:
        a["recommended"] = bool(a["rule_passed"])

    def sort_key(a):
        return (
            a["recommended"],
            a["raw"] if a["raw"] is not None else -1,
            a["hook"] if a["hook"] is not None else -1,
        )

    for p in projects_out:
        assessed = sorted(p.pop("_assessed"), key=sort_key, reverse=True)
        p["total_clips"] = len(assessed)
        p["recommended"] = sum(1 for a in assessed if a["recommended"])
        p["clips"] = assessed[:top_n_per_project] if top_n_per_project else assessed

    all_assessments.sort(key=sort_key, reverse=True)
    return {
        "rules": {**DEFAULT_RULES, **(rules or {})},
        "projects_analyzed": analyzed,
        "excluded_projects": excluded,
        "total_clips": len(all_assessments),
        "recommended_total": sum(1 for a in all_assessments if a["recommended"]),
        "projects": sorted(projects_out, key=lambda p: p["recommended"], reverse=True),
    }
