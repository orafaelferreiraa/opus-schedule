"""Testes do relatório de qualidade da biblioteca."""

import json

import azure.functions as func

import function_app
from shared.library_report import build_library_report


def _clip(cid, score, hook, dur_ms, title="t"):
    return {
        "id": cid,
        "title": title,
        "durationMs": dur_ms,
        "score": score,
        "judgeResult": {"hookScore": hook, "hookComment": "hook desc"},
    }


class FakeClient:
    def __init__(self, projects, clips_by_pid):
        self._projects = projects
        self._clips = clips_by_pid

    def list_projects(self):
        return self._projects

    def get_clips_by_project(self, pid):
        return self._clips.get(pid, [])


def test_report_ranks_and_recommends():
    projects = [{"projectId": "P1", "sourceInfo": {"title": "Ep1"}}]
    clips = {
        "P1": [
            _clip("P1.a", 99, 9, 60000),    # ok
            _clip("P1.b", 70, 9, 60000),    # score baixo
            _clip("P1.c", 99, 3, 60000),    # hook baixo
            _clip("P1.d", 99, 9, 200000),   # longo demais
        ]
    }
    rep = build_library_report(FakeClient(projects, clips), min_score=85, min_hook=6, min_dur_s=15, max_dur_s=100)
    assert rep["projects_analyzed"] == 1
    assert rep["total_clips"] == 4
    assert rep["recommended_total"] == 1
    p = rep["projects"][0]
    # ordenado por score desc (99s primeiro)
    assert p["clips"][0]["score"] == 99
    rec = [c["id"] for c in p["clips"] if c["recommended"]]
    assert rec == ["P1.a"]


def test_report_excludes_personal_by_default():
    projects = [{"projectId": "P30318211wd3"}, {"projectId": "P1", "sourceInfo": {"title": "Ep"}}]
    clips = {"P1": [_clip("P1.a", 99, 9, 60000)]}
    rep = build_library_report(FakeClient(projects, clips))
    assert "P30318211wd3" in rep["excluded_projects"]
    assert rep["projects_analyzed"] == 1


def test_report_explicit_project_ids_override():
    clips = {"PX": [_clip("PX.a", 99, 9, 60000)]}
    rep = build_library_report(FakeClient([], clips), project_ids=["PX"], exclude_project_ids=[])
    assert rep["projects_analyzed"] == 1
    assert rep["total_clips"] == 1


def test_analyze_library_endpoint(patch_telemetry):
    projects = [{"projectId": "P1", "sourceInfo": {"title": "Ep1"}}]
    clips = {"P1": [_clip("P1.a", 99, 9, 60000), _clip("P1.b", 50, 9, 60000)]}
    patch_telemetry.setattr(function_app, "OpusClient", lambda: FakeClient(projects, clips))

    req = func.HttpRequest(
        method="POST",
        url="http://localhost/api/analyze-library",
        body=json.dumps({"min_score": 85}).encode(),
        headers={"Content-Type": "application/json"},
    )
    resp = function_app.analyze_library(req)
    payload = json.loads(resp.get_body())
    assert resp.status_code == 200
    assert payload["total_clips"] == 2
    assert payload["recommended_total"] == 1
