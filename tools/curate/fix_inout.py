"""Conserto de in/out de cortes truncados (cortados no meio) — LowOpsCast.

A OpusClip às vezes corta a ideia no começo/fim. Este tool usa a transcrição COMPLETA
do episódio (GET /transcripts, com timings palavra-a-palavra) pra mostrar o que está
logo ANTES e logo DEPOIS da janela atual do corte, e propor um in/out estendido que
inclua o setup/payoff faltando.

`timeRanges` do clip é gravável (`[[startMs, endMs]]`); a correção só materializa no
render (publish/export de coleção).

Modos:
  inspect  — mostra a janela de transcrição em volta do corte (antes | dentro | depois)
  apply    — grava novo timeRanges via PUT (guardado atrás de --yes)

Uso:
  python tools/curate/fix_inout.py inspect --project P... --clip P....xxxx [--window 30]
  python tools/curate/fix_inout.py apply --project P... --clip P....xxxx --start 3820.0 --end 3925.0 --yes
"""

from __future__ import annotations

import argparse
import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(REPO, "src")
sys.path.insert(0, SRC)


def _load_settings():
    cfg = json.load(open(os.path.join(SRC, "local.settings.json")))["Values"]
    for k, v in cfg.items():
        os.environ.setdefault(k, v)
    os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"] = ""


def _headers():
    h = {"Authorization": f"Bearer {os.environ['OPUSCLIP_API_KEY']}", "Content-Type": "application/json"}
    if os.environ.get("OPUSCLIP_ORG_ID"):
        h["x-opus-org-id"] = os.environ["OPUSCLIP_ORG_ID"]
    return h


def _fetch_transcript_segments(pid: str) -> list[dict]:
    import httpx

    r = httpx.get(
        "https://api.opus.pro/api/transcripts",
        headers=_headers(),
        params={"q": "findByProjectId", "projectId": pid},
        timeout=60,
    )
    r.raise_for_status()
    data = r.json().get("data", [])
    # data = [[seg, seg, ...]] — desembrulha o nível externo
    segs = data[0] if (isinstance(data, list) and data and isinstance(data[0], list)) else data
    return [s for s in segs if isinstance(s, dict)]


def _clip_range_s(pid: str, clip_id: str):
    from shared.opus_client import OpusClient

    for c in OpusClient().get_clips_by_project(pid):
        if c.get("id") == clip_id:
            tr = c.get("timeRanges") or []
            # timeRanges em ms; usa 1º início e último fim
            start = tr[0][0] / 1000.0
            end = tr[-1][1] / 1000.0
            return start, end, c
    raise SystemExit(f"clip {clip_id} não encontrado em {pid}")


def _clean(txt: str) -> str:
    return " ".join(txt.replace("__silence", "·").split())


def cmd_inspect(args):
    _load_settings()
    cstart, cend, _clip = _clip_range_s(args.project, args.clip)
    segs = _fetch_transcript_segments(args.project)
    w = args.window
    print(f"Corte {args.clip}")
    print(f"Janela atual: {cstart:.1f}s → {cend:.1f}s  ({cend - cstart:.1f}s)\n")

    def show(tag, lo, hi):
        picked = [s for s in segs if s.get("end", 0) > lo and s.get("start", 0) < hi]
        text = _clean(" ".join(str(s.get("text", "")) for s in picked))
        if picked:
            print(f"--- {tag}  [{picked[0].get('start',0):.1f}s → {picked[-1].get('end',0):.1f}s] ---")
            print(text[:900] + ("…" if len(text) > 900 else ""))
        else:
            print(f"--- {tag}: (vazio) ---")
        print()

    show(f"ANTES do corte (−{w}s) — setup que pode estar faltando", cstart - w, cstart)
    show("DENTRO do corte (o que vai hoje)", cstart, cend)
    show(f"DEPOIS do corte (+{w}s) — payoff/fechamento que pode estar faltando", cend, cend + w)

    # sugestão automática: estender pro início da frase que contém cstart e pro fim da que contém cend
    starts = [s for s in segs if s.get("start", 0) <= cstart <= s.get("end", 0)]
    ends = [s for s in segs if s.get("start", 0) <= cend <= s.get("end", 0)]
    sug_start = starts[0]["start"] if starts else cstart
    sug_end = ends[0]["end"] if ends else cend
    print(f"Sugestão simples (alinhar às fronteiras de frase): {sug_start:.1f}s → {sug_end:.1f}s")
    print("Revise a janela ANTES/DEPOIS acima e escolha start/end pra um raciocínio fechado; depois:")
    print(f"  python tools/curate/fix_inout.py apply --project {args.project} --clip {args.clip} "
          f"--start <S> --end <E> --yes")


def cmd_apply(args):
    _load_settings()
    import httpx

    _, _, clip = _clip_range_s(args.project, args.clip)
    old_tr = clip.get("timeRanges")
    new_tr = [[int(round(args.start * 1000)), int(round(args.end * 1000))]]
    print(f"timeRanges: {old_tr}  →  {new_tr}")
    if not args.yes:
        print("DRY-RUN (sem --yes): nada gravado.")
        return
    r = httpx.put(
        f"https://api.opus.pro/api/exportable-clips/{args.clip}",
        headers=_headers(),
        json={"timeRanges": new_tr},
        timeout=30,
    )
    print("PUT status:", r.status_code)
    print("(o novo in/out só vira vídeo no próximo render — publish ou export de coleção)")


def main():
    p = argparse.ArgumentParser(description="Conserto de in/out de cortes truncados.")
    sub = p.add_subparsers(dest="cmd", required=True)
    pi = sub.add_parser("inspect")
    pi.add_argument("--project", required=True)
    pi.add_argument("--clip", required=True)
    pi.add_argument("--window", type=float, default=30.0)
    pi.set_defaults(func=cmd_inspect)
    pa = sub.add_parser("apply")
    pa.add_argument("--project", required=True)
    pa.add_argument("--clip", required=True)
    pa.add_argument("--start", type=float, required=True)
    pa.add_argument("--end", type=float, required=True)
    pa.add_argument("--yes", action="store_true")
    pa.set_defaults(func=cmd_apply)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
