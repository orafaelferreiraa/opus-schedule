"""Testes do relatório de qualidade da biblioteca."""

import json

import azure.functions as func

import function_app
from shared import library_report
from shared.library_report import build_library_report

CLEAN_TEXT = (
    "hoje vamos falar sobre arquitetura de nuvem escalabilidade seguranca "
    "observabilidade pipelines entrega continua kubernetes containers rede "
    "custos performance confiabilidade automacao infraestrutura como codigo terraform"
)


def _clip(cid, raw=36, hook=10, coh=10, conn=9, dur_ms=60000, text=CLEAN_TEXT):
    return {
        "id": cid,
        "title": "titulo",
        "durationMs": dur_ms,
        "text": text,
        "judgeResult": {
            "score": raw,
            "hookScore": hook,
            "coherenceScore": coh,
            "connectionScore": conn,
        },
    }


class FakeClient:
    def __init__(self, projects, clips_by_pid):
        self._projects = projects
        self._clips = clips_by_pid

    def list_projects(self):
        return self._projects

    def get_clips_by_project(self, pid):
        return self._clips.get(pid, [])


def _find(report, cid):
    for p in report["projects"]:
        for c in p["clips"]:
            if c["id"] == cid:
                return c
    raise AssertionError(f"clip {cid} não encontrado")


def test_rigorous_rules_filter():
    projects = [{"projectId": "P1", "sourceInfo": {"title": "Ep1"}}]
    clips = {
        "P1": [
            _clip("P1.ok"),                                        # passa
            _clip("P1.rawlow", raw=34),                            # raw < 35
            _clip("P1.pausas", text=("boa " + "__silence bom " * 9)),  # 9 pausas/min > 6
            _clip("P1.reps", text="pra pra pra pra tudo aqui agora"),   # 3 repetições
            _clip("P1.longo", dur_ms=200000),                      # duração > 90s
        ]
    }
    rep = build_library_report(FakeClient(projects, clips), use_llm=False)
    assert rep["total_clips"] == 5
    assert rep["recommended_total"] == 1
    assert _find(rep, "P1.ok")["recommended"] is True
    assert _find(rep, "P1.rawlow")["recommended"] is False
    assert any("raw" in r for r in _find(rep, "P1.rawlow")["rule_reasons"])
    assert any("pausas" in r for r in _find(rep, "P1.pausas")["rule_reasons"])
    assert any("repet" in r for r in _find(rep, "P1.reps")["rule_reasons"])
    assert any("duração" in r for r in _find(rep, "P1.longo")["rule_reasons"])


def test_speech_signals_exposed():
    projects = [{"projectId": "P1"}]
    clips = {"P1": [_clip("P1.a")]}
    c = _find(build_library_report(FakeClient(projects, clips)), "P1.a")
    for field in ("pauses_per_min", "reps", "cutoffs", "filler_pct", "raw", "hook", "coherence", "connection"):
        assert field in c


def test_excludes_personal_by_default():
    projects = [{"projectId": "P30318211wd3"}, {"projectId": "P1"}]
    clips = {"P1": [_clip("P1.a")]}
    rep = build_library_report(FakeClient(projects, clips))
    assert "P30318211wd3" in rep["excluded_projects"]
    assert rep["projects_analyzed"] == 1


def test_llm_annotates_but_does_not_gate(monkeypatch):
    monkeypatch.setenv("JUDGE_AZURE_OPENAI_ENDPOINT", "https://foundry.example")
    calls = []

    def fake_llm(clip, settings):
        calls.append(clip.get("id"))
        return {"ok": True, "score": 72, "approve": False, "flags": ["filler"], "reason": "aparar fillers"}

    monkeypatch.setattr(library_report, "llm_assess", fake_llm)
    projects = [{"projectId": "P1"}]
    clips = {"P1": [_clip("P1.ok"), _clip("P1.bad", raw=20)]}
    rep = build_library_report(FakeClient(projects, clips), use_llm=True)

    assert rep["llm_used"] is True
    ok = _find(rep, "P1.ok")
    # regra passa -> recomendado, mesmo o LLM tendo approve=False (LLM só anota)
    assert ok["recommended"] is True
    assert ok["llm"]["reason"] == "aparar fillers"
    # LLM roda só nos recomendados por padrão (não no P1.bad que falhou nas regras)
    assert calls == ["P1.ok"]
    assert _find(rep, "P1.bad")["recommended"] is False


def test_analyze_library_endpoint(patch_telemetry):
    projects = [{"projectId": "P1", "sourceInfo": {"title": "Ep1"}}]
    clips = {"P1": [_clip("P1.ok"), _clip("P1.bad", raw=20)]}
    patch_telemetry.setattr(function_app, "OpusClient", lambda: FakeClient(projects, clips))

    req = func.HttpRequest(
        method="POST",
        url="http://localhost/api/analyze-library",
        body=json.dumps({"use_llm": False}).encode(),
        headers={"Content-Type": "application/json"},
    )
    resp = function_app.analyze_library(req)
    payload = json.loads(resp.get_body())
    assert resp.status_code == 200
    assert payload["total_clips"] == 2
    assert payload["recommended_total"] == 1
    assert payload["llm_used"] is False
