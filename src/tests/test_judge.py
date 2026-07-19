import json

from shared.judge import JudgeSettings, _build_auth_headers, _safe_json, _run_hard_rules


def test_safe_json_parses_expected_contract():
    payload = {
        "final_score": 77,
        "soft_signals": {
            "rhythm": 70,
            "clarity": 75,
            "context": 80,
            "engagement": 78,
            "pauses": 65,
        },
        "audit_reason": "Clip coeso com ritmo moderado.",
    }

    parsed = _safe_json(json.dumps(payload))

    assert parsed["final_score"] == 77
    assert parsed["soft_signals"]["clarity"] == 75
    assert "coeso" in parsed["audit_reason"]


def test_hard_rules_reject_short_duration_and_weak_text():
    settings = JudgeSettings.from_request({"judge_mode": "rules_only"})
    clip = {
        "id": "P1.C1",
        "projectId": "P1",
        "title": "",
        "description": "",
        "durationMs": 1000,
    }

    reasons = _run_hard_rules(clip, settings)

    assert "duration_too_short" in reasons
    assert "text_too_short" in reasons


def test_judge_settings_defaults_to_api_key_auth_mode_when_missing_env(monkeypatch):
    monkeypatch.delenv("JUDGE_AUTH_MODE", raising=False)

    settings = JudgeSettings.from_request({"judge_mode": "off"})

    assert settings.auth_mode == "api_key"


def test_build_auth_headers_uses_api_key(monkeypatch):
    monkeypatch.setenv("JUDGE_AZURE_OPENAI_API_KEY", "k-test")

    settings = JudgeSettings.from_request({"judge_mode": "off"})
    headers = _build_auth_headers(settings)

    assert headers["api-key"] == "k-test"
    assert headers["Content-Type"] == "application/json"
