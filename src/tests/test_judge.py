from shared.judge import JudgeSettings, _run_hard_rules, judge_clips, summarize_judge


def _good_clip() -> dict:
    return {
        "id": "P1.C1",
        "projectId": "P1",
        "title": "Título com substância suficiente",
        "description": "descrição",
        "durationMs": 45000,
    }


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


def test_rules_only_approves_clip_passing_hard_rules():
    settings = JudgeSettings.from_request({"judge_mode": "rules_only"})

    [result] = judge_clips([_good_clip()], settings)

    assert result["decision"] == "APPROVE"
    assert result["final_score"] == 100
    assert result["source"] == "rules_only"


def test_rules_only_rejects_clip_failing_hard_rules():
    settings = JudgeSettings.from_request({"judge_mode": "rules_only"})
    clip = {**_good_clip(), "durationMs": 1000, "title": "", "description": ""}

    [result] = judge_clips([clip], settings)

    assert result["decision"] == "REJECT"
    assert result["source"] == "rules_only"
    assert result["hard_fail_reasons"]


def test_off_mode_approves_without_evaluating():
    settings = JudgeSettings.from_request({"judge_mode": "off"})

    [result] = judge_clips([_good_clip()], settings)

    assert result["decision"] == "APPROVE"
    assert result["source"] == "disabled"


def test_summarize_counts_decisions_and_sources():
    settings = JudgeSettings.from_request({"judge_mode": "rules_only"})
    good = _good_clip()
    bad = {**_good_clip(), "id": "P1.C2", "durationMs": 1000, "title": "", "description": ""}

    summary = summarize_judge(judge_clips([good, bad], settings))

    assert summary["total"] == 2
    assert summary["approved"] == 1
    assert summary["rejected"] == 1
    assert summary["source_rules_only"] == 2
