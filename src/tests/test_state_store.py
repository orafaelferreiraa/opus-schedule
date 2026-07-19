"""Testes de idempotência do ScheduleStateStore (sem Azure real)."""

from azure.core.exceptions import ResourceNotFoundError

from shared.state_store import ScheduleStateStore


class FakeTable:
    """Table client em memória que imita get_entity/upsert_entity."""

    def __init__(self):
        self.entities = {}

    def get_entity(self, partition_key, row_key):
        key = (partition_key, row_key)
        if key not in self.entities:
            raise ResourceNotFoundError("not found")
        return self.entities[key]

    def upsert_entity(self, entity, mode=None):
        self.entities[(entity["PartitionKey"], entity["RowKey"])] = entity


def _store_with_fake():
    store = ScheduleStateStore.__new__(ScheduleStateStore)
    store._table = FakeTable()
    return store


def test_disabled_without_config(monkeypatch):
    monkeypatch.delenv("STORAGE_ACCOUNT_NAME", raising=False)
    monkeypatch.delenv("STATE_STORAGE_CONNECTION_STRING", raising=False)
    store = ScheduleStateStore()
    assert store.enabled is False
    plan = {"YOUTUBE": [{"projectId": "P", "clipId": "c1"}]}
    filtered, skipped = store.filter_plan(plan)
    assert filtered == plan
    assert skipped == 0


def test_mark_and_check_roundtrip():
    store = _store_with_fake()
    assert store.already_scheduled("P", "c1", "YOUTUBE") is False
    store.mark_scheduled("P", "c1", "YOUTUBE")
    assert store.already_scheduled("P", "c1", "YOUTUBE") is True
    # rede diferente é chave diferente
    assert store.already_scheduled("P", "c1", "TIKTOK_BUSINESS") is False


def test_filter_plan_removes_already_scheduled():
    store = _store_with_fake()
    store.mark_scheduled("P", "c1", "YOUTUBE", "2026-01-01T00:00:00.000Z", "s1")
    plan = {
        "YOUTUBE": [
            {"projectId": "P", "clipId": "c1"},
            {"projectId": "P", "clipId": "c2"},
        ]
    }
    filtered, skipped = store.filter_plan(plan)
    assert skipped == 1
    assert [item["clipId"] for item in filtered["YOUTUBE"]] == ["c2"]


def test_network_emptied_is_dropped_from_plan():
    store = _store_with_fake()
    store.mark_scheduled("P", "c1", "YOUTUBE")
    plan = {"YOUTUBE": [{"projectId": "P", "clipId": "c1"}]}
    filtered, skipped = store.filter_plan(plan)
    assert filtered == {}
    assert skipped == 1
