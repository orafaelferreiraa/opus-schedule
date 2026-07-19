"""Fixtures e stubs compartilhados entre os testes.

Centraliza os dummies de telemetria (antes duplicados em test_function_app.py e
test_e2e_schedule_existing_clips.py) para novos testes reutilizarem via a fixture
``patch_telemetry``.
"""

from contextlib import contextmanager

import pytest


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


# Nomes dos contadores/histogramas expostos por function_app que devem ser
# neutralizados durante os testes de handler.
_COUNTERS = (
    "invocation_counter",
    "clips_found_counter",
    "schedules_planned_counter",
    "schedules_created_counter",
    "schedules_failed_counter",
    "schedules_skipped_counter",
    "judge_clips_total_counter",
    "judge_clips_approved_counter",
    "judge_clips_review_counter",
    "judge_clips_rejected_counter",
)
_HISTOGRAMS = ("execution_duration_ms", "judge_latency_ms")


@pytest.fixture
def patch_telemetry(monkeypatch):
    """Substitui tracer, contadores e histogramas de function_app por dummies."""
    import function_app

    monkeypatch.setattr(function_app, "tracer", DummyTracer())
    for name in _COUNTERS:
        if hasattr(function_app, name):
            monkeypatch.setattr(function_app, name, DummyCounter())
    for name in _HISTOGRAMS:
        if hasattr(function_app, name):
            monkeypatch.setattr(function_app, name, DummyHistogram())
    return monkeypatch
