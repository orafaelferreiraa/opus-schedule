"""Testes unitários para a matriz de cadência."""

import pytest
from datetime import datetime
from zoneinfo import ZoneInfo
from shared.schedule_matrix import build_schedule_plan, _next_slot, NETWORK_CONFIG

BRT = ZoneInfo("America/Sao_Paulo")

MOCK_CLIPS = [
    {
        "id": "P0000001.CU000001",
        "projectId": "P0000001",
        "curationId": "CU000001",
        "durationMs": 60000,
        "title": "DevOps: Cultura ou Cargo?",
        "description": "Reflexão sobre o mercado",
        "hashtags": "#DevOps #Cloud",
    },
    {
        "id": "P0000001.CU000002",
        "projectId": "P0000001",
        "curationId": "CU000002",
        "durationMs": 45000,
        "title": "Kubernetes na Prática",
        "description": "Como usar K8s no dia a dia",
        "hashtags": "#K8s #DevOps",
    },
    {
        "id": "P0000001.CU000003",
        "projectId": "P0000001",
        "curationId": "CU000003",
        "durationMs": 30000,
        "title": "IaC com Terraform",
        "description": "Infra como código",
        "hashtags": "#Terraform #IaC",
    },
]

MOCK_ACCOUNTS = [
    {"id": "acc_yt", "postAccountId": "acc_yt", "subAccountId": None, "platform": "YOUTUBE"},
    {"id": "acc_tt", "postAccountId": "acc_tt", "subAccountId": None, "platform": "TIKTOK_BUSINESS"},
    {"id": "acc_ig", "postAccountId": "acc_ig", "subAccountId": "sub_ig", "platform": "INSTAGRAM_BUSINESS"},
    {"id": "acc_li", "postAccountId": "acc_li", "subAccountId": "sub_li", "platform": "LINKEDIN"},
    {"id": "acc_fb", "postAccountId": "acc_fb", "subAccountId": "sub_fb", "platform": "FACEBOOK_PAGE"},
]


def test_plan_has_all_platforms():
    plan = build_schedule_plan(MOCK_CLIPS, MOCK_ACCOUNTS)
    assert set(plan.keys()) == {"YOUTUBE", "TIKTOK_BUSINESS", "INSTAGRAM_BUSINESS", "LINKEDIN", "FACEBOOK_PAGE"}


def test_youtube_gets_all_clips():
    plan = build_schedule_plan(MOCK_CLIPS, MOCK_ACCOUNTS)
    assert len(plan["YOUTUBE"]) == len(MOCK_CLIPS)


def test_instagram_limited_to_top_n():
    plan = build_schedule_plan(MOCK_CLIPS, MOCK_ACCOUNTS)
    top_n = NETWORK_CONFIG["INSTAGRAM_BUSINESS"]["top_n"]
    assert len(plan["INSTAGRAM_BUSINESS"]) <= top_n


def test_linkedin_limited_to_top_n():
    plan = build_schedule_plan(MOCK_CLIPS, MOCK_ACCOUNTS)
    top_n = NETWORK_CONFIG["LINKEDIN"]["top_n"]
    assert len(plan["LINKEDIN"]) <= top_n


def test_clip_id_is_bare():
    """clipId não deve conter o projectId com ponto."""
    plan = build_schedule_plan(MOCK_CLIPS, MOCK_ACCOUNTS)
    for items in plan.values():
        for item in items:
            assert "." not in item["clipId"], f"clipId contém ponto: {item['clipId']}"


def test_publish_at_is_future():
    plan = build_schedule_plan(MOCK_CLIPS, MOCK_ACCOUNTS)
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    for items in plan.values():
        for item in items:
            dt = datetime.fromisoformat(item["publishAt"].replace("Z", "+00:00"))
            assert dt > now, f"publishAt no passado: {item['publishAt']}"


def test_description_contains_cta():
    plan = build_schedule_plan(MOCK_CLIPS, MOCK_ACCOUNTS)
    for items in plan.values():
        for item in items:
            assert "@LowOps" in item["description"]


def test_no_schedules_when_no_accounts():
    plan = build_schedule_plan(MOCK_CLIPS, [])
    assert plan == {}


def test_missing_platform_account_skipped():
    accounts_without_linkedin = [a for a in MOCK_ACCOUNTS if a["platform"] != "LINKEDIN"]
    plan = build_schedule_plan(MOCK_CLIPS, accounts_without_linkedin)
    assert "LINKEDIN" not in plan


def test_next_slot_respects_days_only():
    # segunda = 0, terça = 1; pedir só ter/qua/qui (1,2,3) a partir de uma segunda
    from_dt = datetime(2026, 7, 20, 10, 0, tzinfo=BRT)  # segunda-feira
    slot = _next_slot(from_dt, [9, 15], days_only=[1, 2, 3])
    assert slot.weekday() in [1, 2, 3], f"Dia inesperado: {slot.weekday()}"


def test_next_slot_chooses_correct_hour():
    from_dt = datetime(2026, 7, 21, 10, 0, tzinfo=BRT)  # terça, 10h
    slot = _next_slot(from_dt, [9, 15], days_only=[])
    assert slot.hour == 15, f"Hora esperada 15, obtida {slot.hour}"
