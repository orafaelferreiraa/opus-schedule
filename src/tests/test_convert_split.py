"""Testes do endpoint convert-clips-to-split."""

import json

import azure.functions as func

import function_app


CLIPS = [
    # já em split
    {"id": "P1.C1", "projectId": "P1", "renderPref": {"enableSplitLayout": True, "enableFillLayout": False}},
    # em fill (precisa converter)
    {"id": "P1.C2", "projectId": "P1", "renderPref": {"enableFillLayout": True, "enableSplitLayout": False}},
    # sem renderPref (não é split → precisa converter)
    {"id": "P1.C3", "projectId": "P1"},
]


class FakeClient:
    def __init__(self):
        self.prepared = []

    def get_clips_by_collection(self, _cid):
        return list(CLIPS)

    def get_clips_by_project(self, _pid):
        return list(CLIPS)

    def list_collections(self):
        # A API real devolve IDs (strings), não objetos.
        return ["col1"]

    def prepare_clips_for_split_layout(self, clips):
        self.prepared = list(clips)
        return [{"id": c["id"], "projectId": c.get("projectId", ""), "ok": True} for c in clips]


def _req(body: dict) -> func.HttpRequest:
    return func.HttpRequest(
        method="POST",
        url="http://localhost/api/convert-clips-to-split",
        body=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )


def _run(monkeypatch, body):
    fake = FakeClient()
    monkeypatch.setattr(function_app, "OpusClient", lambda: fake)
    resp = function_app.convert_clips_to_split(_req(body))
    return resp, json.loads(resp.get_body()), fake


def test_missing_target_returns_400(patch_telemetry):
    resp, payload, _ = _run(patch_telemetry, {})
    assert resp.status_code == 400
    assert "collection_id" in payload["error"]


def test_dry_run_reports_only_fill(patch_telemetry):
    resp, payload, fake = _run(patch_telemetry, {"collection_id": "col1", "dry_run": True})
    assert resp.status_code == 200
    assert payload["dry_run"] is True
    assert payload["total_clips"] == 3
    assert payload["already_split"] == 1
    assert payload["to_convert"] == 2
    assert set(payload["to_convert_ids"]) == {"P1.C2", "P1.C3"}
    assert fake.prepared == []  # dry_run não altera nada


def test_only_fill_false_targets_all(patch_telemetry):
    _, payload, _ = _run(patch_telemetry, {"collection_id": "col1", "dry_run": True, "only_fill": False})
    assert payload["to_convert"] == 3


def test_limit_caps_targets(patch_telemetry):
    _, payload, _ = _run(patch_telemetry, {"collection_id": "col1", "dry_run": True, "limit": 1})
    assert payload["to_convert"] == 1


def test_convert_executes_and_reports(patch_telemetry):
    resp, payload, fake = _run(patch_telemetry, {"collection_id": "col1", "dry_run": False})
    assert resp.status_code == 200
    assert payload["dry_run"] is False
    assert payload["converted"] == 2
    assert payload["failed"] == 0
    assert {c["id"] for c in fake.prepared} == {"P1.C2", "P1.C3"}


def test_all_collections_enumerates(patch_telemetry):
    _, payload, _ = _run(patch_telemetry, {"all_collections": True, "dry_run": True})
    assert payload["sources"] == ["collection:col1"]
    assert payload["total_clips"] == 3
