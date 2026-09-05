"""Passo 3 do harness de curadoria local: relatório + plano de agendamento (DRY-RUN).

Lê ``review/<projectId>/clips.json`` (do prep.py) e ``review/<projectId>/verdicts.json``
(escrito por mim, Claude, aplicando a rubrica), funde os veredictos nos cortes e:

- marca ``recommended = gate mecânico passou E eu aprovei o conteúdo``;
- anexa ``_content_score`` (meu final_score) aos aprovados — a mesma "ponte" que o
  function_app fazia com o score do Foundry, agora vinda da minha curadoria;
- roda ``build_schedule_plan`` (rede × horário × top-N) e **imprime o plano SEM criar
  nada na OpusClip** (não chama create_schedules);
- renderiza ``review/<projectId>/report.md`` no estilo de ``cortes-recomendados.md``.

Uso:
    python tools/curate/plan.py --project-id P3083113Va84
"""

from __future__ import annotations

import argparse
import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(REPO, "src")
sys.path.insert(0, SRC)

_EDITOR_URL = "https://clip.opus.pro/editor-ux/{full_id}?clipId={clip_id}"


def _load_settings() -> None:
    cfg = json.load(open(os.path.join(SRC, "local.settings.json")))["Values"]
    for key, value in cfg.items():
        os.environ.setdefault(key, value)
    os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"] = ""


def _clip_id(full_id: str) -> str:
    return full_id.split(".", 1)[1] if "." in full_id else full_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Relatório + plano de agendamento dry-run.")
    parser.add_argument("--project-id", required=True, help="projectId (mesma pasta do prep.py)")
    parser.add_argument(
        "--no-accounts",
        action="store_true",
        help="não consultar contas sociais (só relatório + prévia de cadência)",
    )
    args = parser.parse_args()

    review_dir = os.path.join(REPO, "review", args.project_id)
    clips_path = os.path.join(review_dir, "clips.json")
    verdicts_path = os.path.join(review_dir, "verdicts.json")
    if not os.path.exists(clips_path):
        raise SystemExit(f"Falta {clips_path}. Rode prep.py primeiro.")
    if not os.path.exists(verdicts_path):
        raise SystemExit(f"Falta {verdicts_path}. Eu (Claude) preciso escrever os veredictos primeiro.")

    _load_settings()
    from shared.schedule_matrix import NETWORK_CONFIG, PLATFORM_PRIORITY, _clip_score, build_schedule_plan

    data = json.load(open(clips_path, encoding="utf-8"))
    project_title = data.get("projectTitle", "")
    clips = data["clips"]
    verdicts = {str(v["id"]): v for v in json.load(open(verdicts_path, encoding="utf-8"))}

    missing = [c["id"] for c in clips if c["id"] not in verdicts]
    if missing:
        print(f"AVISO: {len(missing)} cortes sem veredicto (serão tratados como reprovados).", file=sys.stderr)

    # Critério PRIMÁRIO = história completa (aprovada por conteúdo E não cortada no meio).
    # Duração NÃO barra: só roteia rede (curto ≤90s → todas; longo >90s → YouTube/LinkedIn).
    # Fala (filler) vira só nota de polimento, nunca exclui.
    LONG_S = 90
    complete: list[dict] = []          # histórias completas (qualquer duração)
    cut_midway: list[dict] = []        # aprovado mas cortado no meio → consertar in/out
    for c in clips:
        v = verdicts.get(c["id"], {})
        approve = bool(v.get("approve"))
        flags = v.get("content_flags") or []
        c["_verdict"] = v
        c["_content_score"] = int(v.get("final_score", 0)) if approve else None
        c["_cut"] = approve and ("corte_no_meio" in flags)
        c["_long"] = c["signals"]["duration_s"] > LONG_S
        c["_polir"] = not c["gate_passed"]  # nota de polimento (não exclui)
        c["_recommended"] = bool(approve and not c["_cut"])  # história completa = agendável
        if not approve:
            continue
        (cut_midway if c["_cut"] else complete).append(c)

    complete.sort(key=lambda c: c["_content_score"] or 0, reverse=True)
    cut_midway.sort(key=lambda c: c["_content_score"] or 0, reverse=True)
    complete_short = [c for c in complete if not c["_long"]]
    complete_long = [c for c in complete if c["_long"]]
    print(f"Projeto {args.project_id}  {project_title}")
    print(f"Histórias completas (agendáveis, qualquer duração): {len(complete)}/{len(clips)}")
    print(f"  · curtas ≤{LONG_S}s (todas as redes): {len(complete_short)}")
    print(f"  · longas >{LONG_S}s (YouTube/LinkedIn): {len(complete_long)}")
    print(f"Cortados no meio (consertar in/out via fix_inout.py): {len(cut_midway)}\n")

    accounts: list[dict] = []
    if not args.no_accounts:
        from shared.opus_client import OpusClient

        try:
            accounts = OpusClient().get_social_accounts()
        except Exception as exc:  # noqa: BLE001
            print(f"AVISO: não consegui listar contas sociais ({type(exc).__name__}); só relatório.", file=sys.stderr)

    _print_plan(complete_short, complete_long, accounts, NETWORK_CONFIG, PLATFORM_PRIORITY)

    report_path = os.path.join(review_dir, "report.md")
    _write_report(report_path, project_title, clips, complete_short, complete_long, cut_midway)
    print(f"\nRelatório: {os.path.relpath(report_path, REPO)}")
    print("DRY-RUN: nenhum agendamento foi criado na OpusClip.")


_LONGFORM = {"YOUTUBE", "LINKEDIN"}  # redes que aceitam corte longo


def _print_plan(complete_short, complete_long, accounts, NETWORK_CONFIG, PLATFORM_PRIORITY) -> None:
    if not (complete_short or complete_long):
        print("Nenhuma história completa — nada a agendar.")
        return
    # roteamento por duração: curtas em todas; longas só em YouTube/LinkedIn
    print("== Prévia de cadência por rede (história completa; longa só em YouTube/LinkedIn) ==")
    for platform in PLATFORM_PRIORITY:
        pool = (complete_short + complete_long) if platform in _LONGFORM else complete_short
        pool = sorted(pool, key=lambda c: c["_content_score"] or 0, reverse=True)
        top_n = NETWORK_CONFIG.get(platform, {}).get("top_n", 5)
        take = pool[:top_n]
        if not take:
            continue
        print(f"\n{platform}: top {len(take)}")
        for c in take:
            tag = "longo" if c["_long"] else "curto"
            print(f"  score={c.get('_content_score')} {c['signals']['duration_s']}s({tag})  {c['title'][:66]}")


def _clip_line(c: dict, show_gate: bool = False) -> list[str]:
    v = c["_verdict"]
    url = _EDITOR_URL.format(full_id=c["id"], clip_id=_clip_id(c["id"]))
    dur = c["signals"]["duration_s"]
    if show_gate:
        tail = "gate: " + "; ".join(c.get("gate_reasons") or ["ok"])
    else:
        speech = ", ".join(v.get("speech_flags") or []) or "fala limpa"
        tail = "fala limpa" if speech == "fala limpa" else f"polir: {speech}"
    return [
        f"- [{c['title']}]({url}) — nota {v.get('final_score')} · {dur}s · {tail}",
        f"  - {v.get('reason', '').strip()}",
    ]


def _write_report(
    path: str,
    project_title: str,
    clips: list[dict],
    complete_short: list[dict],
    complete_long: list[dict],
    cut_midway: list[dict],
) -> None:
    total_completas = len(complete_short) + len(complete_long)
    lines = [
        "# Cortes recomendados para postar — LowOpsCast",
        f"\n**{project_title}**",
        f"\n**{total_completas} histórias completas** (início/meio/fim) de {len(clips)} cortes — "
        f"{len(complete_short)} curtas + {len(complete_long)} longas. "
        f"Mais {len(cut_midway)} cortados no meio (a consertar).",
        "\n> Critério primário = história completa que um humano assiste até o fim. Duração NÃO barra: "
        "só roteia a rede. `polir` = fala a limpar antes de postar (não impede). Rubrica em "
        "`src/shared/curation_rubric.md`.\n",
        f"\n## Histórias completas — curtas ≤90s (todas as redes)  ({len(complete_short)})\n",
    ]
    for c in complete_short:
        lines += _clip_line(c)

    lines.append(f"\n## Histórias completas — longas >90s (YouTube/LinkedIn)  ({len(complete_long)})\n")
    if complete_long:
        lines.append("> História completa, só longa demais pra short vertical. Vão bem em vídeo longo.\n")
    for c in complete_long:
        lines += _clip_line(c)

    if cut_midway:
        lines.append(
            f"\n## Cortados no meio — consertar in/out antes de postar  ({len(cut_midway)})\n"
        )
        lines.append(
            "> Conteúdo bom, mas o Opus cortou o começo/fim no meio do raciocínio. Recupere com "
            "`tools/curate/fix_inout.py inspect --project <pid> --clip <id>` e ajuste o in/out.\n"
        )
        for c in cut_midway:
            lines += _clip_line(c)

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
