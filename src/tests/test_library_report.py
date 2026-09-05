"""Testes do relatório de qualidade da biblioteca."""

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


def test_mechanical_gate_filters_speech_issues():
    projects = [{"projectId": "P1", "sourceInfo": {"title": "Ep1"}}]
    clips = {
        "P1": [
            _clip("P1.ok"),
            _clip("P1.pausas", text=("boa " + "__silence bom " * 15)),  # 15 pausas/min > 13.3
            _clip("P1.reps", text="pra pra pra pra tudo aqui agora"),
            _clip("P1.longo", dur_ms=200000),
        ]
    }
    rep = build_library_report(FakeClient(projects, clips))
    assert rep["total_clips"] == 4
    # recommended = só o gate mecânico
    assert _find(rep, "P1.ok")["recommended"] is True
    assert _find(rep, "P1.pausas")["recommended"] is False
    assert any("pausas" in r for r in _find(rep, "P1.pausas")["rule_reasons"])
    assert any("repet" in r for r in _find(rep, "P1.reps")["rule_reasons"])
    assert any("duração" in r for r in _find(rep, "P1.longo")["rule_reasons"])


def test_mechanical_gate_ignores_opus_native_scores():
    # raw/hook/coherence/connection altos NÃO bastam para passar se a fala for ruim,
    # e raw/hook baixos NÃO reprovam se a fala estiver limpa (só informativo agora).
    projects = [{"projectId": "P1"}]
    clips = {"P1": [_clip("P1.lowscore_cleanspeech", raw=10, hook=1, coh=1, conn=1)]}
    rep = build_library_report(FakeClient(projects, clips))
    c = _find(rep, "P1.lowscore_cleanspeech")
    assert c["recommended"] is True
    assert c["raw"] == 10  # ainda reportado, só não usado no gate


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
