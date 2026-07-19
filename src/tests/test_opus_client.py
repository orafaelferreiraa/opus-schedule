import os

from shared.opus_client import OpusClient


def test_prepare_clips_for_split_layout_sends_ai_enhancement_flags(monkeypatch):
    monkeypatch.setenv("OPUSCLIP_API_KEY", "dummy")
    monkeypatch.delenv("OPUSCLIP_ORG_ID", raising=False)

    client = OpusClient()
    calls = []

    monkeypatch.setattr(client, "_put", lambda path, json: calls.append((path, json)) or "")

    updated = client.prepare_clips_for_split_layout([
        {"id": "P1.C1", "projectId": "P1"},
        {"id": "P1.C2", "projectId": "P1"},
    ])

    assert updated == [
        {"id": "P1.C1", "projectId": "P1", "ok": True},
        {"id": "P1.C2", "projectId": "P1", "ok": True},
    ]
    expected_render_pref = {
        "renderPref": {
            "enableSplitLayout": True,
            "enableFillLayout": False,
            "enableFitLayout": False,
            "disableFillLayout": True,
            "disableFitLayout": True,
            "layoutAspectRatio": "portrait",
        }
    }
    assert calls == [
        ("/exportable-clips/P1.C1", expected_render_pref),
        ("/exportable-clips/P1.C2", expected_render_pref),
    ]


def test_prepare_clips_for_split_layout_continues_on_error(monkeypatch):
    monkeypatch.setenv("OPUSCLIP_API_KEY", "dummy")
    monkeypatch.delenv("OPUSCLIP_ORG_ID", raising=False)

    client = OpusClient()

    def fake_put(path, json):
        if path.endswith("C1"):
            raise RuntimeError("boom")
        return ""

    monkeypatch.setattr(client, "_put", fake_put)

    updated = client.prepare_clips_for_split_layout([
        {"id": "P1.C1", "projectId": "P1"},
        {"id": "P1.C2", "projectId": "P1"},
    ])

    assert updated[0]["ok"] is False and "boom" in updated[0]["error"]
    assert updated[1]["ok"] is True