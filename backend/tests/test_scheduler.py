"""Scheduler + push delivery tests (Rubric A2)."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from coach.integrations import CalendarEvent, StubCalendarClient, StubHealthKitClient
from coach.lifecycle import Coach
from coach.llm import LLMClient
from coach.push import LoggingPushDelivery
from coach.scheduler import Scheduler, active_users_from_store
from coach.store import Store


def _utc(y, m, d, h=9):
    return datetime(y, m, d, h, 0, tzinfo=timezone.utc)


def _setup_user(store, push, user_id="u1"):
    cal = StubCalendarClient()
    hk = StubHealthKitClient()
    coach = Coach(user_id, "fitness", store, LLMClient(), cal, hk)
    coach.nudge_engine.push = push
    coach.record_intake({"experience": "novice", "days_per_week": "3"})
    coach.build_program("strong + energetic")
    cal.seed(user_id, [])
    return coach, cal, hk


def test_scheduler_fires_for_active_users():
    store = Store(":memory:")
    push = LoggingPushDelivery()
    _setup_user(store, push, "u1")
    _setup_user(store, push, "u2")

    cal = StubCalendarClient()
    hk = StubHealthKitClient()
    sched = Scheduler(
        store=store, llm=LLMClient(), calendar=cal, healthkit=hk, push=push,
        active_users=active_users_from_store(store),
    )
    res = sched.run_tick(now=_utc(2026, 5, 25, 9))
    assert res.users_evaluated == 2
    # Pushes were delivered through the transport.
    assert len(push.records) == len(res.nudges_fired)


def test_scheduler_respects_restraint_across_ticks():
    """Multiple ticks in the same day must not exceed the daily nudge cap."""
    store = Store(":memory:")
    push = LoggingPushDelivery()
    _setup_user(store, push, "u1")

    cal = StubCalendarClient()
    hk = StubHealthKitClient()
    sched = Scheduler(
        store=store, llm=LLMClient(), calendar=cal, healthkit=hk, push=push,
        active_users=active_users_from_store(store),
    )
    fired = 0
    for h in range(7, 22, 1):
        res = sched.run_tick(now=_utc(2026, 5, 25, h))
        fired += len(res.nudges_fired)
    # Daily cap = 2 (see NudgeEngine.DAILY_NUDGE_CAP).
    assert fired <= 2, f"scheduler must respect daily cap, fired {fired}"


def test_push_delivery_receives_nudge():
    store = Store(":memory:")
    push = LoggingPushDelivery()
    coach, _, _ = _setup_user(store, push, "u1")
    push.register_device("u1", "fake-token-abc")
    n = coach.try_nudge(now=_utc(2026, 5, 25))
    assert n is not None
    assert push.records, "push transport must receive the nudge"
    assert push.records[-1].nudge_id == n.id
