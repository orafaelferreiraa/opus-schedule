"""Atribuição de fala por corte (diarização).

Para vídeos em que o Rafael é ENTREVISTADO (ou co-apresenta), queremos só os cortes
em que a substância é FALADA por ele. Usa GET /transcripts (que traz speaker + timings
palavra-a-palavra) e cruza com o timeRanges de cada corte pra medir a fração de palavras
ditas por cada locutor dentro do corte.

Modos:
  roster    — lista os locutores do projeto (tempo de fala + amostra) pra identificar quem é quem
  attribute — dado --me <speaker_id>, calcula por corte a fração de palavras suas; escreve speakers.json

Uso:
  python tools/curate/speaker_filter.py roster --project P...
  python tools/curate/speaker_filter.py attribute --project P... --me speaker_2 [--min 0.6]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(REPO, "src")
sys.path.insert(0, SRC)
cfg = json.load(open(os.path.join(SRC, "local.settings.json")))["Values"]
for k, v in cfg.items():
    os.environ.setdefault(k, v)
os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"] = ""

import httpx  # noqa: E402
from shared.opus_client import OpusClient  # noqa: E402

H = {"Authorization": f"Bearer {os.environ['OPUSCLIP_API_KEY']}", "Content-Type": "application/json"}
if os.environ.get("OPUSCLIP_ORG_ID"):
    H["x-opus-org-id"] = os.environ["OPUSCLIP_ORG_ID"]


def segments(pid):
    r = httpx.get("https://api.opus.pro/api/transcripts", headers=H,
                  params={"q": "findByProjectId", "projectId": pid}, timeout=60)
    r.raise_for_status()
    data = r.json().get("data", [])
    segs = data[0] if (isinstance(data, list) and data and isinstance(data[0], list)) else data
    return [s for s in segs if isinstance(s, dict)]


def flat_words(segs):
    """(start_s, speaker) por palavra real (ignora __silence)."""
    out = []
    for s in segs:
        spk = s.get("speaker")
        words = s.get("words") or []
        if words:
            for w in words:
                txt = str(w.get("word", "")).strip()
                if txt and txt != "__silence" and w.get("start") is not None:
                    out.append((w["start"], spk))
        else:
            # fallback: distribui palavras uniformemente no segmento
            txt = str(s.get("text", "")).strip()
            toks = [t for t in txt.split() if t and t != "__silence"]
            a, b = s.get("start", 0), s.get("end", 0)
            n = max(1, len(toks))
            for i, _ in enumerate(toks):
                out.append((a + (b - a) * i / n, spk))
    return out


def cmd_roster(args):
    segs = segments(args.project)
    talk = {}
    sample = {}
    for s in segs:
        spk = s.get("speaker")
        dur = (s.get("end", 0) or 0) - (s.get("start", 0) or 0)
        txt = str(s.get("text", "")).strip()
        if txt in ("", "__silence"):
            continue
        talk[spk] = talk.get(spk, 0) + dur
        if spk not in sample and len(txt) > 25:
            sample[spk] = txt[:120]
    total = sum(talk.values()) or 1
    print(f"Projeto {args.project} — locutores:")
    for spk, t in sorted(talk.items(), key=lambda x: -x[1]):
        print(f"  {spk}: {t/60:.1f} min ({100*t/total:.0f}% do falado)")
        print(f"      ex: {sample.get(spk,'')}")


def cmd_attribute(args):
    words = flat_words(segments(args.project))
    words.sort()
    clips = OpusClient().get_clips_by_project(args.project)
    out = {}
    print(f"Projeto {args.project} — atribuição por corte (você = {args.me}; corte é 'seu' se >= {args.min:.0%}):\n")
    kept = 0
    for c in clips:
        tr = c.get("timeRanges") or []
        ranges = [(a / 1000.0, b / 1000.0) for a, b in tr]
        by = {}
        for st, spk in words:
            if any(a <= st <= b for a, b in ranges):
                by[spk] = by.get(spk, 0) + 1
        tot = sum(by.values()) or 1
        me_share = by.get(args.me, 0) / tot
        dominant = max(by, key=by.get) if by else None
        mine = me_share >= args.min
        kept += 1 if mine else 0
        out[c["id"]] = {"me_share": round(me_share, 2), "dominant": dominant, "by_speaker": by}
        tag = "VOCÊ" if mine else "outros"
        print(f"  [{tag:6}] você={me_share:4.0%}  dom={dominant}  {c.get('title','')[:52]}")
    with open(os.path.join(REPO, "review", args.project, "speakers.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\nCortes majoritariamente SEUS (>= {args.min:.0%}): {kept}/{len(clips)}. Escrito review/{args.project}/speakers.json")


def cmd_clipturns(args):
    """Escreve, por corte, a transcrição quebrada em TURNOS de fala (relabelados por corte
    como Voz A/B/C na ordem de aparição — evita herdar o rótulo global que a Opus troca).
    O julgamento de 'quem é o entrevistado' fica pro conteúdo, não pro rótulo."""
    segs = segments(args.project)
    clips = OpusClient().get_clips_by_project(args.project)
    out_dir = os.path.join(REPO, "review", args.project)
    lines = [f"# Turnos de fala por corte — {args.project}",
             "\n> Vozes relabeladas POR CORTE (A/B/C na ordem em que aparecem). A Opus troca os",
             "> rótulos globais, então NÃO assuma que 'Voz A' é a mesma pessoa entre cortes.",
             "> Numa entrevista, o ENTREVISTADO é quem dá a resposta longa/substancial em 1ª pessoa;",
             "> os hosts fazem pergunta curta, vinheta, patrocínio, banter.\n"]
    for c in clips:
        tr = c.get("timeRanges") or []
        ranges = [(a / 1000.0, b / 1000.0) for a, b in tr]
        inside = [s for s in segs if any(a <= s.get("start", 0) <= b for a, b in ranges)
                  and str(s.get("text", "")) not in ("", "__silence")]
        # relabel local
        local = {}
        turns = []
        for s in inside:
            spk = s.get("speaker")
            if spk not in local:
                local[spk] = chr(ord("A") + len(local))
            lab = local[spk]
            txt = _clean(s.get("text", ""))
            if turns and turns[-1][0] == lab:
                turns[-1][1] += " " + txt
            else:
                turns.append([lab, txt])
        lines.append(f"\n---\n\n## {c.get('title','')}\n\n- id: `{c['id']}`  ·  vozes distintas: {len(local)}\n")
        for lab, txt in turns:
            lines.append(f"**Voz {lab}:** {txt}")
    with open(os.path.join(out_dir, "clip_turns.md"), "w", encoding="utf-8") as f:
        f.write("\n\n".join(lines))
    print(f"escrito review/{args.project}/clip_turns.md ({len(clips)} cortes)")


def _clean(t):
    return " ".join(str(t).replace("__silence", " ").split())


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("roster"); pr.add_argument("--project", required=True); pr.set_defaults(func=cmd_roster)
    pc = sub.add_parser("clipturns"); pc.add_argument("--project", required=True); pc.set_defaults(func=cmd_clipturns)
    pa = sub.add_parser("attribute")
    pa.add_argument("--project", required=True)
    pa.add_argument("--me", required=True)
    pa.add_argument("--min", type=float, default=0.6)
    pa.set_defaults(func=cmd_attribute)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
