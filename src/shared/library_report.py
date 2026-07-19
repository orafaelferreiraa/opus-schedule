"""
Relatório de qualidade da biblioteca de cortes (OpusClip).

Enumera os projetos, lê os cortes e avalia quais valem postar combinando:
- gate mecânico: limpeza da fala da transcrição (pausas, repetições, gaguejo, filler) + duração;
- veredito de CONTEÚDO do LLM gpt-5-mini (opcional): o corte tem substância/payoff real
  para o público do LowOpsCast, não apenas fala limpa e coerente.

`recommended` = passou no gate mecânico E (se use_llm) o LLM aprovou o CONTEÚDO.
Sinais nativos da OpusClip (raw/hook/coherence/connection) são só informativos — não
discriminam substância (verificado empiricamente: anedotas fracas recebem nota alta).
Independe do layout. O mesmo código roda local ou dentro do Function App.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from shared.clip_quality import (
    DEFAULT_RULES,
    LLMSettings,
    _num,
    extract_speech_signals,
    llm_assess,
    rule_verdict,
)

# Projetos que são vídeos pessoais do Rafael — fora da automação (ver memória).
DEFAULT_EXCLUDE_PROJECT_IDS = {"P30318211wd3", "P3020416EqOU", "P3020716CxZv"}


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
        "_clip": clip,  # temporário para o LLM; removido antes de serializar
    }


def build_library_report(
    client,
    *,
    project_ids: list[str] | None = None,
    exclude_project_ids: set[str] | list[str] | None = None,
    rules: dict | None = None,
    use_llm: bool = False,
    llm_scope: str = "candidates",
    max_workers: int = 10,
    top_n_per_project: int | None = None,
) -> dict:
    """Monta o relatório de qualidade. `client` é um OpusClient (ou compatível).

    `llm_scope`: "candidates" (default) roda o LLM só nos que passaram o gate
    mecânico; "all" roda em todos os cortes.
    """
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

    llm_used = False
    llm_settings = LLMSettings() if use_llm else None
    if use_llm and llm_settings and llm_settings.enabled:
        targets = all_assessments if llm_scope == "all" else [a for a in all_assessments if a["rule_passed"]]
        if targets:
            llm_used = True
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                verdicts = list(pool.map(lambda a: llm_assess(a["_clip"], llm_settings), targets))
            for a, v in zip(targets, verdicts):
                a["llm"] = {k: v[k] for k in ("ok", "score", "approve", "content_flags", "speech_flags", "reason")}

    # Decisão final: gate mecânico E (se LLM rodou nesse item) aprovação de conteúdo.
    for a in all_assessments:
        llm = a.get("llm")
        content_ok = (llm is None) or (bool(llm.get("ok")) and bool(llm.get("approve")))
        a["recommended"] = bool(a["rule_passed"] and content_ok)
        a.pop("_clip", None)

    def _llm_score(a):
        llm = a.get("llm") or {}
        return llm["score"] if llm.get("ok") and llm.get("score") is not None else -1

    def sort_key(a):
        return (
            a["recommended"],
            _llm_score(a),
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
        "llm_used": llm_used,
        "projects_analyzed": analyzed,
        "excluded_projects": excluded,
        "total_clips": len(all_assessments),
        "recommended_total": sum(1 for a in all_assessments if a["recommended"]),
        "projects": sorted(projects_out, key=lambda p: p["recommended"], reverse=True),
    }
