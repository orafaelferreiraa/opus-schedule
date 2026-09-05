"""Agrega a curadoria de todos os projetos em review/ e imprime a tabela final.

Para cada projeto com clips.json + verdicts.json, cruza gate mecânico × aprovação de
conteúdo e reporta: total, gate-passed, content-approved, recommended (gate AND approve),
e content-approved-but-gate-blocked. Não faz rede.
"""

from __future__ import annotations

import glob
import json
import os

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def main() -> None:
    rows = []
    tot = {"clips": 0, "content": 0, "complete": 0, "short": 0, "long": 0, "cut": 0, "competitor": 0}
    for clips_path in sorted(glob.glob(os.path.join(REPO, "review", "*", "clips.json"))):
        pdir = os.path.dirname(clips_path)
        vpath = os.path.join(pdir, "verdicts.json")
        if not os.path.exists(vpath):
            continue
        data = json.load(open(clips_path, encoding="utf-8"))
        clips = data["clips"]
        verdicts = {str(v["id"]): v for v in json.load(open(vpath, encoding="utf-8"))}
        title = (data.get("projectTitle") or data["projectId"])[:52]

        def _approve(c):
            return bool(verdicts.get(c["id"], {}).get("approve"))

        def _cut(c):
            return "corte_no_meio" in (verdicts.get(c["id"], {}).get("content_flags") or [])

        def _long(c):
            return c["signals"]["duration_s"] > 90

        n = len(clips)
        content = sum(1 for c in clips if _approve(c))
        complete = sum(1 for c in clips if _approve(c) and not _cut(c))          # história completa, qualquer duração
        short = sum(1 for c in clips if _approve(c) and not _cut(c) and not _long(c))
        long_ = sum(1 for c in clips if _approve(c) and not _cut(c) and _long(c))
        cut = sum(1 for c in clips if _approve(c) and _cut(c))
        comp = sum(1 for v in verdicts.values() if "critica_concorrente_nomeado" in (v.get("content_flags") or []))
        missing = [c["id"] for c in clips if c["id"] not in verdicts]

        rows.append((title, n, content, complete, short, long_, cut, comp, len(missing)))
        for k, val in (("clips", n), ("content", content), ("complete", complete),
                       ("short", short), ("long", long_), ("cut", cut), ("competitor", comp)):
            tot[k] += val

    hdr = f"{'Episódio':<52}{'clips':>6}{'conteúdo':>9}{'COMPLETA':>9}{'curta':>6}{'longa':>6}{'corte':>6}{'anti-c':>7}"
    print(hdr)
    print("-" * len(hdr))
    for title, n, content, complete, short, long_, cut, comp, miss in rows:
        flag = f"  ⚠{miss}" if miss else ""
        print(f"{title:<52}{n:>6}{content:>9}{complete:>9}{short:>6}{long_:>6}{cut:>6}{comp:>7}{flag}")
    print("-" * len(hdr))
    print(f"{'TOTAL':<52}{tot['clips']:>6}{tot['content']:>9}{tot['complete']:>9}{tot['short']:>6}{tot['long']:>6}{tot['cut']:>6}{tot['competitor']:>7}")
    print()
    print("Legenda: conteúdo=aprovado na rubrica · COMPLETA=história completa agendável (aprovado + fecha "
          "raciocínio, QUALQUER duração) · curta ≤90s (todas as redes) · longa >90s (YouTube/LinkedIn) · "
          "corte=aprovado mas cortado no meio (consertar in/out) · anti-c=reprovado por crítica a concorrente.")


if __name__ == "__main__":
    main()
