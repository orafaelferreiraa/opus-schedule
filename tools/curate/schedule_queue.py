"""Fila de postagem LowOpsCast + marca pessoal.

Monta o calendário real de postagem a partir das histórias completas curadas em review/*/:
- 2 baldes: podcast (substância do convidado) e pessoal (o Rafael falando).
- Roteamento por rede: YouTube/TikTok = volume (2/dia, proporcional ~2,5 podcast:pessoal);
  Instagram/LinkedIn = curado (nota alta, cadência baixa, crescimento orgânico do perfil pessoal).
- CTA "link na bio" em toda descrição.

Dry-run por padrão (imprime + grava review/_queue/); `--apply` cria os agendamentos de verdade.
Reusa a mecânica de horários de shared/schedule_matrix (não altera o NETWORK_CONFIG de produção).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(REPO, "src")
sys.path.insert(0, SRC)


def _load_settings():
    cfg = json.load(open(os.path.join(SRC, "local.settings.json")))["Values"]
    for k, v in cfg.items():
        os.environ.setdefault(k, v)
    os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"] = ""


# ---- baldes ----
PODCAST_PIDS = ["P3090317kFfo", "P3090317kaRt", "P3090317jt4X", "P3090317jbEo", "P3090317jHpG",
                "P3090317j1uw", "P3090317ieTV", "P3090317iMs2", "P3090317hgSM", "P3090317hEKl",
                "P3090317X8tZ"]
PERSONAL_SOLO = ["P30318211wd3", "P3020716CxZv", "P3020416EqOU"]
PERSONAL_INTERVIEW = ["P3090319KC5s", "P3090317f12p", "P3090402YL1N"]  # filtra is_rafael

CTA = "Quer conferir o vídeo completo? 👉 link na bio"
CURATED_MIN_SCORE = 70
_EDITOR = "https://clip.opus.pro/editor-ux/{fid}?clipId={cid}"

# cadência por rede (override local — não toca no NETWORK_CONFIG de produção)
# gaps escolhidos p/ o _next_slot (que usa '>' estrito): 6h faz 12h+19h caírem no mesmo dia (2/dia);
# 20h no LinkedIn faz cair de madrugada e o slot das 9h valer em seg/ter/qui sem pular a terça.
NET = {
    "YOUTUBE":            {"hours": [12, 19], "gap": 6,  "days": []},
    "TIKTOK_BUSINESS":    {"hours": [12, 20], "gap": 7,  "days": []},  # TikTok puxa mais pra noite
    "INSTAGRAM_BUSINESS": {"hours": [18],     "gap": 20, "days": []},  # Reels: noite (18h), todo dia
    "LINKEDIN":           {"hours": [17],     "gap": 20, "days": [0, 1, 3]},   # seg/ter/qui, 17h (vídeo B2B)
}


def _bare(full_id):
    return full_id.split(".", 1)[1] if "." in full_id else full_id


def _desc(clip):
    parts = [str(clip.get("description", "")).strip(), str(clip.get("hashtags", "")).strip()]
    body = "\n\n".join(p for p in parts if p)
    return ((body + "\n\n" if body else "") + CTA)[:2000]


def _entry(clip, verdict, source):
    return {
        "id": clip["id"], "clipId": _bare(clip["id"]), "projectId": clip.get("projectId", ""),
        "title": clip.get("title", ""), "description": _desc(clip),
        "dur": clip["signals"]["duration_s"], "score": int(verdict.get("final_score") or 0),
        "source": source,
    }


def _read(pid):
    clips = json.load(open(os.path.join(REPO, "review", pid, "clips.json")))["clips"]
    V = {v["id"]: v for v in json.load(open(os.path.join(REPO, "review", pid, "verdicts.json")))}

    def _opt(name):
        p = os.path.join(REPO, "review", pid, name)
        return {x["id"]: x for x in json.load(open(p))} if os.path.exists(p) else {}

    return clips, V, _opt("speaker_verdict.json"), _opt("host_verdict.json")


def _complete(clip, V):
    v = V.get(clip["id"], {})
    return bool(v.get("approve")) and "corte_no_meio" not in (v.get("content_flags") or [])


def collect():
    """Agrupa por FONTE (episódio/talk) para permitir round-robin — nunca repetir a pessoa em
    sequência. Cada grupo já vem ordenado por nota (melhor primeiro)."""
    pod_groups, per_groups = {}, {}
    for pid in PODCAST_PIDS:
        clips, V, _spk, host = _read(pid)
        for c in clips:
            if not _complete(c, V):
                continue
            if host.get(c["id"], {}).get("is_rafael"):  # corte do host resgatado -> pessoal
                per_groups.setdefault("host:" + pid, []).append(_entry(c, V[c["id"]], "personal"))
            else:
                pod_groups.setdefault(pid, []).append(_entry(c, V[c["id"]], "podcast"))
    for pid in PERSONAL_SOLO:
        clips, V, _spk, _h = _read(pid)
        for c in clips:
            if _complete(c, V):
                per_groups.setdefault(pid, []).append(_entry(c, V[c["id"]], "personal"))
    for pid in PERSONAL_INTERVIEW:
        clips, V, spk, _h = _read(pid)
        for c in clips:
            if _complete(c, V) and spk.get(c["id"], {}).get("is_rafael"):
                per_groups.setdefault(pid, []).append(_entry(c, V[c["id"]], "personal"))
    for g in list(pod_groups.values()) + list(per_groups.values()):
        g.sort(key=lambda e: -e["score"])
    return pod_groups, per_groups


def round_robin(groups):
    """Achata grupos rodando 1 de cada por vez (round-robin), então nunca sai 2 seguidos da mesma
    fonte. Grupos ordenados por nota do melhor corte (episódios mais fortes lideram cada rodada)."""
    cols = sorted([list(g) for g in groups if g], key=lambda g: -g[0]["score"])
    out = []
    r = 0
    while True:
        took = False
        for col in cols:
            if r < len(col):
                out.append(col[r]); took = True
        if not took:
            break
        r += 1
    return out


def weave(a, b):
    """Intercala proporcional: os dois esgotam juntos (pega o balde mais 'atrasado' na sua fração)."""
    out, i, j = [], 0, 0
    while i < len(a) or j < len(b):
        pa = i / len(a) if a else 1.0
        pb = j / len(b) if b else 1.0
        if j >= len(b) or (i < len(a) and pa <= pb):
            out.append(a[i]); i += 1
        else:
            out.append(b[j]); j += 1
    return out


def schedule(cfg, queue):
    from shared.schedule_matrix import BRT, _next_slot
    dt = datetime.now(BRT)
    rows = []
    for e in queue:
        slot = _next_slot(dt, cfg["hours"], cfg["days"])
        rows.append((slot, e))
        dt = slot + timedelta(hours=cfg["gap"])
    return rows


def _cur(groups):
    return {k: [e for e in g if e["score"] >= CURATED_MIN_SCORE] for k, g in groups.items()}


def build_queues():
    pod_groups, per_groups = collect()
    # fila plana com round-robin por episódio/fonte (nunca repete a pessoa em sequência)
    podcast = round_robin(pod_groups.values())
    personal = round_robin(per_groups.values())
    volume = weave(podcast, personal)
    curated = weave(round_robin(_cur(pod_groups).values()), round_robin(_cur(per_groups).values()))
    return {
        "YOUTUBE": volume, "TIKTOK_BUSINESS": volume,
        "INSTAGRAM_BUSINESS": curated, "LINKEDIN": curated,
    }, podcast, personal


def main():
    ap = argparse.ArgumentParser(description="Fila de postagem (dry-run por padrão).")
    ap.add_argument("--apply", action="store_true", help="cria os agendamentos de verdade na OpusClip")
    ap.add_argument("--limit", type=int, default=0, help="no --apply, cria só os N primeiros por rede (lote de teste; 0 = todos)")
    ap.add_argument("--date", default="", help="no --apply, cria só os posts DESSA data BRT (YYYY-MM-DD)")
    ap.add_argument("--preview", type=int, default=10, help="quantos posts mostrar por rede no terminal")
    args = ap.parse_args()
    _load_settings()

    queues, podcast, personal = build_queues()
    print(f"Baldes: podcast={len(podcast)}  pessoal={len(personal)}  total={len(podcast)+len(personal)}")
    print(f"Curado (nota≥{CURATED_MIN_SCORE}): podcast={sum(1 for e in podcast if e['score']>=CURATED_MIN_SCORE)}"
          f" + pessoal={sum(1 for e in personal if e['score']>=CURATED_MIN_SCORE)}\n")

    plan = {}
    md = ["# Fila de postagem — LowOpsCast + marca pessoal\n",
          f"Baldes: **{len(podcast)} podcast + {len(personal)} pessoal = {len(podcast)+len(personal)}**. "
          f"CTA em toda descrição: _{CTA}_\n"]
    dias = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
    for net, cfg in NET.items():
        rows = schedule(cfg, queues[net])
        plan[net] = rows
        n_pod = sum(1 for _, e in rows if e["source"] == "podcast")
        header = f"## {net} — {len(rows)} posts ({n_pod} podcast / {len(rows)-n_pod} pessoal)"
        print(header)
        md.append(f"\n{header}\n")
        for k, (slot, e) in enumerate(rows):
            line = (f"{dias[slot.weekday()]} {slot.strftime('%d/%m %H:%M')}  [{e['source']:7}] "
                    f"nota {e['score']:>3}  {e['title'][:52]}")
            if k < args.preview:
                print("  " + line)
            md.append(f"- {dias[slot.weekday()]} {slot.strftime('%d/%m %H:%M')} · "
                      f"[{e['source']}] nota {e['score']} · [{e['title']}]"
                      f"({_EDITOR.format(fid=e['id'], cid=e['clipId'])})")
        if len(rows) > args.preview:
            print(f"  … +{len(rows)-args.preview} (lista completa no .md)")
        print()

    out_dir = os.path.join(REPO, "review", "_queue")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "posting_plan.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    with open(os.path.join(out_dir, "posting_plan.json"), "w", encoding="utf-8") as f:
        json.dump({net: [{"publishAt_brt": s.isoformat(), **e} for s, e in rows]
                   for net, rows in plan.items()}, f, ensure_ascii=False, indent=2)
    print(f"Plano gravado em review/_queue/posting_plan.md (+ .json)")

    if not args.apply:
        print("\nDRY-RUN: nenhum agendamento criado. Use --apply depois de revisar (e confira que as "
              "contas certas — IG/LinkedIn pessoais — estão conectadas na OpusClip).")
        return

    if args.date:
        plan = {net: [(s, e) for (s, e) in rows if s.strftime("%Y-%m-%d") == args.date]
                for net, rows in plan.items()}
        n = sum(len(v) for v in plan.values())
        print(f"\n** SÓ A DATA {args.date}: {n} posts **")
    if args.limit:
        plan = {net: rows[: args.limit] for net, rows in plan.items()}
        print(f"\n** LOTE DE TESTE: só os {args.limit} primeiros por rede **")
    _apply(plan)


# Quando a rede tem VÁRIAS contas/páginas, escolher a certa pelo nome (senão pega a errada).
# LinkedIn tem 7 páginas de comunidade + o perfil pessoal; queremos o PESSOAL do Rafael.
PREFERRED_ACCOUNT = {"LINKEDIN": "Rafael Ferreira"}


def _pick_account(net, accs):
    want = PREFERRED_ACCOUNT.get(net)
    if want:
        for a in accs:
            if str(a.get("extUserName", "")).strip().lower() == want.lower():
                return a
        print(f"AVISO: conta preferida '{want}' não achada em {net}; contas: "
              f"{[a.get('extUserName') for a in accs]}. Pulando {net} por segurança.")
        return None
    return accs[0]


_LEDGER = os.path.join(REPO, "review", "_queue", "scheduled.json")


def _load_ledger():
    return set(json.load(open(_LEDGER))) if os.path.exists(_LEDGER) else set()


def _save_ledger(done):
    os.makedirs(os.path.dirname(_LEDGER), exist_ok=True)
    json.dump(sorted(done), open(_LEDGER, "w"), ensure_ascii=False, indent=2)


def _apply(plan):
    from shared.opus_client import OpusClient
    client = OpusClient()
    accounts = client.get_social_accounts()
    by_plat = {}
    for a in accounts:
        by_plat.setdefault(str(a.get("platform", "")).upper(), []).append(a)

    done = _load_ledger()  # idempotência local: "NET|clipId" já agendados
    api_plan = {}
    for net, rows in plan.items():
        accs = by_plat.get(net, [])
        if not accs:
            print(f"AVISO: rede {net} sem conta conectada — pulando {len(rows)} posts.")
            continue
        acc = _pick_account(net, accs)
        if acc is None:
            continue
        rows = [(s, e) for (s, e) in rows if f"{net}|{e['clipId']}" not in done]
        if not rows:
            print(f"{net}: todos já agendados (ledger) — nada a fazer.")
            continue
        print(f"{net}: postando como '{acc.get('extUserName')}' ({len(rows)} novos)")
        items = []
        for slot, e in rows:
            it = {
                "clipId": e["clipId"], "projectId": e["projectId"],
                "postAccountId": acc.get("postAccountId") or acc.get("id", ""),
                "title": e["title"][:100], "description": e["description"],
                "publishAt": slot.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            }
            if acc.get("subAccountId"):
                it["subAccountId"] = acc["subAccountId"]
            items.append(it)
        api_plan[net] = items

    total = sum(len(v) for v in api_plan.values())
    print(f"\nAPPLY: criando {total} agendamentos (1 req/s)...")
    results = client.create_schedules(api_plan)
    ok = 0
    for r in results:
        if r.get("ok"):
            ok += 1
            done.add(f"{str(r.get('network','')).upper()}|{r.get('clipId','')}")
    _save_ledger(done)
    print(f"criados {ok}/{len(results)} (falhas: {len(results)-ok}). Ledger: {len(done)} agendados no total.")


if __name__ == "__main__":
    main()
