"""Weekly local-notification plan (coach/reminders.py + /notifications/plan)."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from coach.reminders import weekly_reminder_plan


def test_three_reminders_per_training_day():
    plan = weekly_reminder_plan(days_per_week=3)
    # 3 training days (mon/wed/fri) x {eve, pre, log} = 9
    assert len(plan) == 9
    kinds = {r.id.split("-")[0] for r in plan}
    assert kinds == {"eve", "pre", "log"}


def test_training_days_match_cadence():
    days = {r.weekday for r in weekly_reminder_plan(days_per_week=2) if r.id.startswith("pre-")}
    assert days == {"mon", "thu"}


def test_night_before_is_previous_evening():
    plan = weekly_reminder_plan(days_per_week=3)
    eve_mon = next(r for r in plan if r.id == "eve-mon")
    assert eve_mon.weekday == "sun" and eve_mon.hour == 20  # Sunday night before Monday


def test_pre_workout_uses_requested_hour_and_identity():
    plan = weekly_reminder_plan(days_per_week=1, identity_statement="I am someone who shows up.", hour=6)
    pre = next(r for r in plan if r.id.startswith("pre-"))
    assert pre.hour == 6
    assert "I am someone who shows up." in pre.body


def test_post_session_offset_and_midnight_guard():
    # Late training hour pushes the log reminder past midnight → dropped.
    plan = weekly_reminder_plan(days_per_week=1, hour=23, post_offset_min=90)
    assert not any(r.id.startswith("log-") for r in plan)
    # A normal hour keeps it, offset applied (17:00 + 90m = 18:30).
    plan2 = weekly_reminder_plan(days_per_week=1, hour=17, post_offset_min=90)
    log = next(r for r in plan2 if r.id.startswith("log-"))
    assert (log.hour, log.minute) == (18, 30)


def test_cadence_clamped():
    assert len(weekly_reminder_plan(days_per_week=99)) == 7 * 3  # clamped to 7 days
    assert len(weekly_reminder_plan(days_per_week=0)) >= 1       # clamped up to >=1


# ---- endpoint ----

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DB", str(tmp_path / "coach.db"))
    if "api.app" in sys.modules:
        del sys.modules["api.app"]
    from api.app import app
    with TestClient(app) as c:
        yield c


def test_endpoint_returns_plan_for_profiled_user(client):
    h = {"X-User-Id": "alice"}
    client.post("/intake/submit", json={
        "answers": {"experience": "novice", "days_per_week": "3", "injuries": "none"},
        "identity_statement": "strong + energetic",
    }, headers=h)
    r = client.get("/notifications/plan", headers=h)
    assert r.status_code == 200
    rems = r.json()["reminders"]
    assert len(rems) == 9
    assert {"id", "weekday", "hour", "minute", "title", "body"} <= set(rems[0].keys())
