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
        {"id": "P1.C1", "projectId": "P1"},
        {"id": "P1.C2", "projectId": "P1"},
    ]
    assert calls == [
        (
            "/exportable-clips/P1.C1",
            {
                "renderPref": {
                    "enableSplitLayout": True,
                    "enableFillLayout": False,
                    "enableFitLayout": False,
                    "disableFillLayout": True,
                    "disableFitLayout": True,
                    "layoutAspectRatio": "portrait",
                    "removeFillerWord": True,
                    "removePause": True,
                    "enableEmoji": False,
                }
            },
        ),
        (
            "/exportable-clips/P1.C2",
            {
                "renderPref": {
                    "enableSplitLayout": True,
                    "enableFillLayout": False,
                    "enableFitLayout": False,
                    "disableFillLayout": True,
                    "disableFitLayout": True,
                    "layoutAspectRatio": "portrait",
                    "removeFillerWord": True,
                    "removePause": True,
                    "enableEmoji": False,
                }
            },
        ),
    ]