"""Passo 1 do harness de curadoria local (Claude Code como juiz).

Coleta os cortes de um projeto OpusClip, roda o gate mecânico determinístico e
escreve dois arquivos em ``review/<projectId>/``:

- ``clips.json``       : dados de cada corte (id, título, duração, scores nativos,
                          gate mecânico, transcrição) — consumido pelo passo 3 (plan.py).
- ``transcripts.md``   : versão legível para EU (Claude) ler e julgar, aplicando a
                          rubrica de ``src/shared/curation_rubric.md``.

Depois deste passo eu escrevo ``review/<projectId>/verdicts.json`` (aprovar/reprovar +
score + motivo), que o ``plan.py`` funde de volta nos cortes. Nenhuma chamada a LLM/Foundry
acontece aqui — a substância de conteúdo é julgada por mim, não por um modelo remoto.

Uso:
    python tools/curate/prep.py --title Paulo
    python tools/curate/prep.py --project-id P3083113Va84
"""

from __future__ import annotations

import argparse
import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(REPO, "src")
sys.path.insert(0, SRC)


def _load_settings() -> None:
    """Carrega as chaves de src/local.settings.json no ambiente (padrão do repo)."""
    cfg = json.load(open(os.path.join(SRC, "local.settings.json")))["Values"]
    for key, value in cfg.items():
        os.environ.setdefault(key, value)
    # Evita que o OpusClient tente exportar telemetria para o App Insights localmente.
    os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"] = ""


def _resolve_project(client, *, project_id: str | None, title: str | None) -> tuple[str, str]:
    """Resolve (projectId, título). Casa por substring de título quando --title é dado."""
    projects = client.list_projects()

    def _pid(p: dict) -> str:
        return str(p.get("projectId") or p.get("id") or "")

    def _title(p: dict) -> str:
        return str((p.get("sourceInfo") or {}).get("title") or p.get("title") or "")

    if project_id:
        for p in projects:
            if _pid(p) == project_id:
                return project_id, _title(p)
        # Projeto não veio na listagem (ex.: q=mine), mas o ID pode ser válido.
        return project_id, ""

    needle = (title or "").lower().strip()
    matches = [p for p in projects if needle in _title(p).lower()]
    if not matches:
        print(f"Nenhum projeto casa com --title {title!r}. Projetos disponíveis:", file=sys.stderr)
        for p in projects:
            print(f"  {_pid(p)}\t{_title(p)}", file=sys.stderr)
        raise SystemExit(2)
    if len(matches) > 1:
        print(f"--title {title!r} é ambíguo, casou {len(matches)} projetos:", file=sys.stderr)
        for p in matches:
            print(f"  {_pid(p)}\t{_title(p)}", file=sys.stderr)
        print("Rode de novo com --project-id <id>.", file=sys.stderr)
        raise SystemExit(2)
    return _pid(matches[0]), _title(matches[0])


def _num(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def main() -> None:
    parser = argparse.ArgumentParser(description="Coleta + gate mecânico de um projeto OpusClip.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--project-id", help="projectId exato (ex.: P3083113Va84)")
    group.add_argument("--title", help="substring do título do projeto (ex.: Paulo)")
    args = parser.parse_args()

    _load_settings()
    from shared.clip_quality import extract_speech_signals, rule_verdict
    from shared.opus_client import OpusClient

    client = OpusClient()
    project_id, project_title = _resolve_project(client, project_id=args.project_id, title=args.title)
    print(f"Projeto: {project_id}  {project_title}")

    clips = client.get_clips_by_project(project_id)
    print(f"Cortes: {len(clips)}")

    prepared: list[dict] = []
    for clip in clips:
        if not isinstance(clip, dict):
            continue
        signals = extract_speech_signals(clip)
        gate = rule_verdict(clip, signals)
        jr = clip.get("judgeResult") or {}
        prepared.append(
            {
                "id": str(clip.get("id", "")),
                "projectId": str(clip.get("projectId", project_id)),
                "title": str(clip.get("title", "") or ""),
                "description": str(clip.get("description", "") or ""),
                "hashtags": str(clip.get("hashtags", "") or ""),
                "durationMs": int(clip.get("durationMs", 0) or 0),
                "rank": clip.get("rank"),
                "score_native": _num(clip.get("score")),
                "native_hook": _num(jr.get("hookScore")),
                "native_coherence": _num(jr.get("coherenceScore")),
                "signals": signals,
                "gate_passed": gate["passed"],
                "gate_reasons": gate["reasons"],
                "text": str(clip.get("text", "") or ""),
            }
        )

    prepared.sort(key=lambda c: (c["rank"] if isinstance(c["rank"], int) else 9999))

    out_dir = os.path.join(REPO, "review", project_id)
    os.makedirs(out_dir, exist_ok=True)

    with open(os.path.join(out_dir, "clips.json"), "w", encoding="utf-8") as f:
        json.dump(
            {"projectId": project_id, "projectTitle": project_title, "clips": prepared},
            f,
            ensure_ascii=False,
            indent=2,
        )

    _write_transcripts_md(out_dir, project_id, project_title, prepared)

    passed = sum(1 for c in prepared if c["gate_passed"])
    print(f"Gate mecânico: {passed}/{len(prepared)} passaram.")
    print(f"Escrito: {os.path.relpath(out_dir, REPO)}/clips.json  e  transcripts.md")
    print("Próximo passo: eu (Claude) leio transcripts.md e escrevo verdicts.json.")


def _write_transcripts_md(out_dir: str, project_id: str, project_title: str, clips: list[dict]) -> None:
    lines: list[str] = [
        f"# Transcrições para curadoria — {project_id}",
        f"\n**{project_title}** · {len(clips)} cortes.",
        "\nJulgue cada corte pela rubrica em `src/shared/curation_rubric.md` e escreva",
        "`verdicts.json` (lista de `{id, approve, final_score, content_flags, speech_flags, reason}`).",
        "O gate mecânico abaixo é só polimento de fala — NÃO decide o approve.\n",
    ]
    for i, c in enumerate(clips, 1):
        s = c["signals"]
        gate = "OK" if c["gate_passed"] else "reprovado: " + ", ".join(c["gate_reasons"])
        transcript = c["text"].replace("__silence", " [pausa] ").strip()
        lines.append(f"\n---\n\n## {i}. {c['title']}")
        lines.append(f"\n- **id**: `{c['id']}`")
        lines.append(f"- duração: {s['duration_s']}s · rank OpusClip: {c['rank']}")
        lines.append(
            f"- gate mecânico: {gate} "
            f"(pausas/min {s['pauses_per_min']}, reps {s['reps']}, gaguejo {s['cutoffs']}, filler {s['filler_pct']}%)"
        )
        lines.append(f"\n> {transcript}\n")
    with open(os.path.join(out_dir, "transcripts.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
