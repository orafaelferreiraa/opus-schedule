import json
from contextlib import contextmanager

import azure.functions as func

import function_app


class DummySpan:
    def set_attribute(self, _key, _value):
        return None

    def set_status(self, _status):
        return None

    def record_exception(self, _exc):
        return None


class DummyTracer:
    @contextmanager
    def start_as_current_span(self, _name):
        yield DummySpan()


class DummyCounter:
    def add(self, _value, _attributes=None):
        return None


class DummyHistogram:
    def record(self, _value, _attributes=None):
        return None


class E2EClient:
    def __init__(self):
        self.updated = []

    def get_social_accounts(self):
        return [
            {"platform": "YOUTUBE", "postAccountId": "acc_yt", "id": "acc_yt"},
            {"platform": "TIKTOK_BUSINESS", "postAccountId": "acc_tt", "id": "acc_tt"},
        ]

    def get_clips_by_collection(self, _collection_id):
        return [
            {
                "id": "P0001.C001",
                "projectId": "P0001",
                "title": "Clip A",
                "description": "Descricao A",
                "hashtags": "#cloud",
                "durationMs": 60000,
            },
            {
                "id": "P0001.C002",
                "projectId": "P0001",
                "title": "Clip B",
                "description": "Descricao B",
                "hashtags": "#devops",
                "durationMs": 45000,
            },
        ]

    def get_clips_by_project(self, _project_id):
        return []

    def prepare_clips_for_split_layout(self, clips):
        self.updated.extend([clip["id"] for clip in clips])
        return [{"id": clip["id"], "projectId": clip.get("projectId", "")} for clip in clips]

    def create_schedules(self, plan):
        results = []
        for network, items in plan.items():
            for item in items:
                results.append(
                    {
                        "ok": True,
                        "clipId": item["clipId"],
                        "network": network,
                        "scheduleId": f"sched-{item['clipId']}",
                    }
                )
        return results


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


def test_e2e_schedule_existing_clips_pipeline(monkeypatch):
    _patch_telemetry(monkeypatch)
    fake_client = E2EClient()
    monkeypatch.setattr(function_app, "OpusClient", lambda: fake_client)

    email_calls = []
    monkeypatch.setattr(function_app, "send_summary_email", lambda **kwargs: email_calls.append(kwargs))

    req = func.HttpRequest(
        method="POST",
        url="http://localhost/api/schedule-existing-clips",
        body=json.dumps({"collection_id": "COL-E2E", "dry_run": False, "auto_prepare_split_layout": True}).encode(),
        headers={"Content-Type": "application/json"},
    )

    response = function_app.schedule_existing_clips(req)
    payload = json.loads(response.get_body())

    assert response.status_code == 200
    assert payload["total_clips"] == 2
    assert payload["clips_updated_for_split_layout"] == 2
    assert payload["scheduled"] >= 2
    assert payload["failed"] == 0
    assert len(email_calls) == 1
    assert fake_client.updated == ["P0001.C001", "P0001.C002"]