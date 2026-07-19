import json
from contextlib import contextmanager

import azure.functions as func

import function_app


class DummySpan:
    def __init__(self):
        self.attributes = {}
        self.status = None
        self.exceptions = []

    def set_attribute(self, key, value):
        self.attributes[key] = value

    def set_status(self, status):
        self.status = status

    def record_exception(self, exc):
        self.exceptions.append(exc)


class DummyTracer:
    @contextmanager
    def start_as_current_span(self, _name):
        yield DummySpan()


class DummyCounter:
    def __init__(self):
        self.calls = []

    def add(self, value, attributes=None):
        self.calls.append((value, attributes or {}))


class DummyHistogram:
    def __init__(self):
        self.calls = []

    def record(self, value, attributes=None):
        self.calls.append((value, attributes or {}))


class FakeClient:
    def __init__(self):
        self.updated = []

    def get_social_accounts(self):
        return [{"platform": "YOUTUBE", "postAccountId": "acc_yt", "id": "acc_yt"}]

    def get_clips_by_collection(self, collection_id):
        return [
            {
                "id": f"P1.{collection_id}",
                "projectId": "P1",
                "title": "Clip 1",
                "durationMs": 1000,
                "renderPref": {"enableSplitLayout": True},
            }
        ]

    def get_clips_by_project(self, project_id):
        return [
            {
                "id": f"{project_id}.C1",
                "projectId": project_id,
                "title": "Clip 1",
                "durationMs": 1000,
                "renderPref": {"enableSplitLayout": True},
            }
        ]

    def prepare_clips_for_split_layout(self, clips):
        self.updated.extend([clip["id"] for clip in clips])
        return [{"id": clip["id"], "projectId": clip.get("projectId", ""), "ok": True} for clip in clips]

    def create_schedules(self, _plan):
        return [{"ok": True, "clipId": "C1", "network": "YOUTUBE", "scheduleId": "S1"}]


def _patch_telemetry(monkeypatch):
    monkeypatch.setattr(function_app, "tracer", DummyTracer())
    monkeypatch.setattr(function_app, "invocation_counter", DummyCounter())
    monkeypatch.setattr(function_app, "clips_found_counter", DummyCounter())
    monkeypatch.setattr(function_app, "schedules_planned_counter", DummyCounter())
    monkeypatch.setattr(function_app, "schedules_created_counter", DummyCounter())
    monkeypatch.setattr(function_app, "schedules_failed_counter", DummyCounter())
    monkeypatch.setattr(function_app, "judge_clips_total_counter", DummyCounter())
    monkeypatch.setattr(function_app, "judge_clips_approved_counter", DummyCounter())
    monkeypatch.setattr(function_app, "judge_clips_review_counter", DummyCounter())
    monkeypatch.setattr(function_app, "judge_clips_rejected_counter", DummyCounter())
    monkeypatch.setattr(function_app, "execution_duration_ms", DummyHistogram())
    monkeypatch.setattr(function_app, "judge_latency_ms", DummyHistogram())


def test_schedule_existing_clips_requires_inputs(monkeypatch):
    _patch_telemetry(monkeypatch)

    req = func.HttpRequest(
        method="POST",
        url="http://localhost/api/schedule-existing-clips",
        body=json.dumps({"dry_run": True}).encode(),
        headers={"Content-Type": "application/json"},
    )

    response = function_app.schedule_existing_clips(req)

    assert response.status_code == 400
    assert json.loads(response.get_body()) == {"error": "Informe 'collection_id' ou 'project_ids'"}


def test_schedule_existing_clips_dry_run(monkeypatch):
    _patch_telemetry(monkeypatch)
    monkeypatch.setattr(function_app, "OpusClient", FakeClient)
    monkeypatch.setattr(
        function_app,
        "build_schedule_plan",
        lambda clips, _accounts: {"YOUTUBE": [{"clipId": clips[0]["id"], "publishAt": "2026-07-20T12:00:00.000Z"}]},
    )

    req = func.HttpRequest(
        method="POST",
        url="http://localhost/api/schedule-existing-clips",
        body=json.dumps({"collection_id": "COL1", "dry_run": True}).encode(),
        headers={"Content-Type": "application/json"},
    )

    response = function_app.schedule_existing_clips(req)
    payload = json.loads(response.get_body())

    assert response.status_code == 200
    assert payload["dry_run"] is True
    assert payload["total_clips"] == 1
    assert "YOUTUBE" in payload["schedule_plan"]


def test_schedule_existing_clips_executes_and_sends_email(monkeypatch):
    _patch_telemetry(monkeypatch)
    fake_client = FakeClient()
    monkeypatch.setattr(function_app, "OpusClient", lambda: fake_client)
    monkeypatch.setattr(
        function_app,
        "build_schedule_plan",
        lambda _clips, _accounts: {"YOUTUBE": [{"clipId": "COL1", "projectId": "P1", "publishAt": "2026-07-20T12:00:00.000Z"}]},
    )

    email_calls = []
    monkeypatch.setattr(function_app, "send_summary_email", lambda **kwargs: email_calls.append(kwargs))

    req = func.HttpRequest(
        method="POST",
        url="http://localhost/api/schedule-existing-clips",
        body=json.dumps({"collection_id": "COL1", "dry_run": False, "auto_prepare_split_layout": True}).encode(),
        headers={"Content-Type": "application/json"},
    )

    response = function_app.schedule_existing_clips(req)
    payload = json.loads(response.get_body())

    assert response.status_code == 200
    assert payload["scheduled"] == 1
    assert payload["failed"] == 0
    assert payload["clips_updated_for_split_layout"] == 1
    assert len(email_calls) == 1
    assert fake_client.updated == ["P1.COL1"]


def test_schedule_existing_clips_filters_to_tiktok_and_one_clip(monkeypatch):
    _patch_telemetry(monkeypatch)
    monkeypatch.setattr(function_app, "OpusClient", FakeClient)
    monkeypatch.setattr(
        function_app,
        "build_schedule_plan",
        lambda _clips, _accounts: {
            "YOUTUBE": [
                {"clipId": "YT1", "projectId": "P1", "publishAt": "2026-07-20T12:00:00.000Z"},
            ],
            "TIKTOK_BUSINESS": [
                {"clipId": "TT1", "projectId": "P1", "publishAt": "2026-07-20T13:00:00.000Z"},
                {"clipId": "TT2", "projectId": "P1", "publishAt": "2026-07-20T14:00:00.000Z"},
            ],
        },
    )

    req = func.HttpRequest(
        method="POST",
        url="http://localhost/api/schedule-existing-clips",
        body=json.dumps(
            {
                "collection_id": "COL1",
                "dry_run": True,
                "target_networks": ["tiktok_business"],
                "max_per_network": 1,
            }
        ).encode(),
        headers={"Content-Type": "application/json"},
    )

    response = function_app.schedule_existing_clips(req)
    payload = json.loads(response.get_body())

    assert response.status_code == 200
    assert set(payload["schedule_plan"].keys()) == {"TIKTOK_BUSINESS"}
    assert len(payload["schedule_plan"]["TIKTOK_BUSINESS"]) == 1


def test_schedule_existing_clips_split_layout_only_filter(monkeypatch):
    _patch_telemetry(monkeypatch)

    class SplitFilterClient(FakeClient):
        def get_clips_by_collection(self, _collection_id):
            return [
                {
                    "id": "P1.C_SPLIT",
                    "projectId": "P1",
                    "title": "Clip split",
                    "durationMs": 1200,
                    "renderPref": {"enableSplitLayout": True},
                },
                {
                    "id": "P1.C_FILL",
                    "projectId": "P1",
                    "title": "Clip fill",
                    "durationMs": 1100,
                    "renderPref": {"enableSplitLayout": False},
                },
            ]

    monkeypatch.setattr(function_app, "OpusClient", SplitFilterClient)

    req = func.HttpRequest(
        method="POST",
        url="http://localhost/api/schedule-existing-clips",
        body=json.dumps(
            {
                "collection_id": "COL1",
                "dry_run": True,
                "split_layout_only": True,
            }
        ).encode(),
        headers={"Content-Type": "application/json"},
    )

    response = function_app.schedule_existing_clips(req)
    payload = json.loads(response.get_body())

    assert response.status_code == 200
    assert payload["total_clips"] == 1


def test_schedule_existing_clips_split_layout_only_excludes_fill_layout(monkeypatch):
    _patch_telemetry(monkeypatch)

    class SplitStrictClient(FakeClient):
        def get_clips_by_collection(self, _collection_id):
            return [
                {
                    "id": "P1.C_SPLIT_FILL",
                    "projectId": "P1",
                    "title": "Clip split+fill",
                    "durationMs": 1200,
                    "renderPref": {"enableSplitLayout": True, "enableFillLayout": True, "enableFitLayout": False},
                },
                {
                    "id": "P1.C_SPLIT_ONLY",
                    "projectId": "P1",
                    "title": "Clip split-only",
                    "durationMs": 1100,
                    "renderPref": {"enableSplitLayout": True, "enableFillLayout": False, "enableFitLayout": False},
                },
            ]

    monkeypatch.setattr(function_app, "OpusClient", SplitStrictClient)

    req = func.HttpRequest(
        method="POST",
        url="http://localhost/api/schedule-existing-clips",
        body=json.dumps(
            {
                "collection_id": "COL1",
                "dry_run": True,
                "split_layout_only": True,
            }
        ).encode(),
        headers={"Content-Type": "application/json"},
    )

    response = function_app.schedule_existing_clips(req)
    payload = json.loads(response.get_body())

    assert response.status_code == 200
    assert payload["total_clips"] == 1
    assert payload["schedule_plan"]["YOUTUBE"][0]["clipId"] == "C_SPLIT_ONLY"


def test_schedule_existing_clips_judge_rules_only_filters_non_approved(monkeypatch):
    _patch_telemetry(monkeypatch)
    monkeypatch.setattr(function_app, "OpusClient", FakeClient)
    monkeypatch.setattr(
        function_app,
        "build_schedule_plan",
        lambda clips, _accounts: {"YOUTUBE": [{"clipId": clips[0]["id"].split(".", 1)[1], "publishAt": "2026-07-20T12:00:00.000Z"}]},
    )
    monkeypatch.setattr(
        function_app,
        "judge_clips",
        lambda clips, _settings: [
            {
                "id": clips[0]["id"],
                "decision": "APPROVE",
                "final_score": 90,
                "hard_fail_reasons": [],
                "soft_signals": {"rules": 90},
                "audit_reason": "approved",
                "source": "rules_only",
            }
        ],
    )

    req = func.HttpRequest(
        method="POST",
        url="http://localhost/api/schedule-existing-clips",
        body=json.dumps({"collection_id": "COL1", "dry_run": True, "judge_mode": "rules_only"}).encode(),
        headers={"Content-Type": "application/json"},
    )

    response = function_app.schedule_existing_clips(req)
    payload = json.loads(response.get_body())

    assert response.status_code == 200
    assert payload["judge"]["mode"] == "rules_only"
    assert payload["judge"]["summary"]["approved"] == 1
    assert payload["total_clips"] == 1
