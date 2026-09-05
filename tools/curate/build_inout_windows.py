"""Extrai, para cada corte truncado (corte_no_meio), a janela de transcrição em volta
(ANTES | DENTRO | DEPOIS, com timestamps) e escreve review/_inout/<pid>.<clip>.md.
Emite review/_inout/manifest.json listando os cortes para o workflow de propostas de in/out.
"""

from __future__ import annotations

import glob
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

client = OpusClient()
H = {"Authorization": f"Bearer {os.environ['OPUSCLIP_API_KEY']}", "Content-Type": "application/json"}
if os.environ.get("OPUSCLIP_ORG_ID"):
    H["x-opus-org-id"] = os.environ["OPUSCLIP_ORG_ID"]


def transcript_segments(pid):
    r = httpx.get("https://api.opus.pro/api/transcripts", headers=H,
                  params={"q": "findByProjectId", "projectId": pid}, timeout=60)
    r.raise_for_status()
    data = r.json().get("data", [])
    segs = data[0] if (isinstance(data, list) and data and isinstance(data[0], list)) else data
    return [s for s in segs if isinstance(s, dict)]


def clean(t):
    return " ".join(str(t).replace("__silence", "·").split())


def window_text(segs, lo, hi):
    picked = [s for s in segs if s.get("end", 0) > lo and s.get("start", 0) < hi]
    if not picked:
        return "(vazio)", lo, hi
    txt = clean(" ".join(str(s.get("text", "")) for s in picked))
    return txt, picked[0].get("start", lo), picked[-1].get("end", hi)


out_dir = os.path.join(REPO, "review", "_inout")
os.makedirs(out_dir, exist_ok=True)
manifest = []
W = 45.0  # janela em segundos de cada lado

for cp in sorted(glob.glob(os.path.join(REPO, "review", "*", "clips.json"))):
    pdir = os.path.dirname(cp)
    pid = os.path.basename(pdir)
    vp = os.path.join(pdir, "verdicts.json")
    if not os.path.exists(vp):
        continue
    verdicts = {v["id"]: v for v in json.load(open(vp, encoding="utf-8"))}
    truncated = [cid for cid, v in verdicts.items()
                 if v.get("approve") and "corte_no_meio" in (v.get("content_flags") or [])]
    if not truncated:
        continue
    tr_by_id = {c["id"]: c.get("timeRanges") for c in client.get_clips_by_project(pid)}
    title_by_id = {c["id"]: c.get("title", "") for c in json.load(open(cp, encoding="utf-8"))["clips"]}
    segs = transcript_segments(pid)
    for cid in truncated:
        tr = tr_by_id.get(cid)
        if not tr:
            continue
        cstart, cend = tr[0][0] / 1000.0, tr[-1][1] / 1000.0
        before, bs, _ = window_text(segs, cstart - W, cstart)
        inside, _, _ = window_text(segs, cstart, cend)
        after, _, ae = window_text(segs, cend, cend + W)
        title = title_by_id.get(cid, "")
        path = os.path.join(out_dir, f"{cid}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\nclip: {cid}\nin/out ATUAL: {cstart:.1f}s → {cend:.1f}s ({cend-cstart:.1f}s)\n")
            f.write(f"janela disponível no fonte: {bs:.1f}s → {ae:.1f}s\n\n")
            f.write(f"## ANTES (setup possivelmente faltando) [{cstart-W:.1f}s → {cstart:.1f}s]\n{before}\n\n")
            f.write(f"## DENTRO (o que vai hoje) [{cstart:.1f}s → {cend:.1f}s]\n{inside}\n\n")
            f.write(f"## DEPOIS (payoff/fechamento possivelmente faltando) [{cend:.1f}s → {cend+W:.1f}s]\n{after}\n")
        manifest.append({"pid": pid, "clip": cid, "title": title,
                         "cstart": round(cstart, 1), "cend": round(cend, 1),
                         "src_lo": round(bs, 1), "src_hi": round(ae, 1),
                         "window_path": os.path.relpath(path, REPO)})

with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)
print(f"janelas escritas: {len(manifest)} em review/_inout/")
for m in manifest:
    print(f"  {m['pid']}  {m['clip']}  {m['cstart']}→{m['cend']}s  {m['title'][:50]}")
