"""
Tests that the load-bearing principles are actually enforced — not just stated
in comments. Each test maps explicitly to a rubric item from Section 12.
"""

from __future__ import annotations

import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from coach.integrations import (
    CalendarEvent,
    HealthSignal,
    StubCalendarClient,
    StubHealthKitClient,
)
from coach.lifecycle import Coach
from coach.llm import LLMClient
from coach.models import NudgeOutcome, VerifiedEvent, WorldState
from coach.store import Store


def _utc(y, m, d, h=9, mn=0):
    return datetime(y, m, d, h, mn, tzinfo=timezone.utc)


@pytest.fixture
def coach():
    store = Store(":memory:")
    cal = StubCalendarClient()
    hk = StubHealthKitClient()
    c = Coach("u1", "fitness", store, LLMClient(), cal, hk)
    return c, store, cal, hk


# ---- Rubric E3 (★) — mirror integrity ---------------------------------------

def test_world_cannot_grow_without_verified_event(coach):
    c, store, _, _ = coach
    profile, _ = c.record_intake({"experience": "novice", "days_per_week": "3"})
    c.build_program("strong + energetic")
    w = store.get_world("u1")
    assert w is not None
    w.currency += 1_000_000

    with pytest.raises(PermissionError):
        store.save_world(w)  # no growth_event → must reject


def test_world_grows_from_report(coach):
    c, store, cal, _ = coach
    c.record_intake({"experience": "novice", "days_per_week": "3"})
    c.build_program("strong + energetic")
    now = _utc(2026, 5, 25)
    cal.seed("u1", [])
    n = c.try_nudge(now=now)
    assert n is not None
    _, ripples, _ = c.record_report(n.id, NudgeOutcome.DONE)
    assert ripples
    assert store.get_world("u1").currency > 0


def test_world_grows_from_sensor(coach):
    c, store, _, hk = coach
    c.record_intake({"experience": "novice", "days_per_week": "3"})
    c.build_program("strong + energetic")
    action, _ = c.prepare_next_action()
    hk.seed(HealthSignal("u1", "workout", _utc(2026, 5, 25, 18), 45.0))
    ripples = c.record_sensor_verification(action.id, "healthkit.workout")
    assert ripples
    assert store.get_world("u1").currency > 0


# ---- Rubric A1 — persistence is real -----------------------------------------

def test_persistence_across_coach_instances(tmp_path):
    db = tmp_path / "coach.db"
    s1 = Store(str(db))
    c1 = Coach("u1", "fitness", s1, LLMClient(), StubCalendarClient(), StubHealthKitClient())
    c1.record_intake({"experience": "novice", "days_per_week": "3"})
    c1.build_program("strong + energetic")
    del c1, s1

    s2 = Store(str(db))
    assert s2.get_profile("u1") is not None
    assert s2.get_program("u1") is not None


# ---- Rubric D3 — restraint --------------------------------------------------

def test_daily_nudge_cap_is_respected(coach):
    c, store, cal, _ = coach
    c.record_intake({"experience": "novice", "days_per_week": "3"})
    c.build_program("strong + energetic")
    now = _utc(2026, 5, 25, 8)
    cal.seed("u1", [])
    fired = 0
    for i in range(6):
        n = c.try_nudge(now=now + timedelta(hours=i * 2))
        if n:
            fired += 1
    assert fired <= c.nudge_engine.DAILY_NUDGE_CAP, "engine must respect daily cap"


def test_engine_backs_off_after_ignored(coach):
    c, store, cal, _ = coach
    c.record_intake({"experience": "novice", "days_per_week": "3"})
    c.build_program("strong + energetic")
    cal.seed("u1", [])
    base = _utc(2026, 5, 25, 8)

    # Force two ignored in a row to trigger backoff.
    for i in range(2):
        n = c.try_nudge(now=base + timedelta(days=i, hours=0))
        assert n is not None
        n.outcome = NudgeOutcome.IGNORED
        n.outcome_at = base + timedelta(days=i, hours=2)
        store.save_nudge(n)

    # Third attempt same-ish day should back off.
    later = base + timedelta(days=1, hours=3)
    decision = c.nudge_engine.decide_timing(
        "u1", c.prepare_next_action()[0], later
    )
    assert not decision.should_fire
    assert "ignored" in decision.reason or "day off" in decision.reason


# ---- Rubric B3 — adaptation, not plan-generation ----------------------------

def test_program_adapts_to_done_report(coach):
    c, store, cal, _ = coach
    c.record_intake({"experience": "novice", "days_per_week": "3"})
    _, _, _, program = c.build_program("strong + energetic")
    starting_squat = program.progression["squat_lb"]
    cal.seed("u1", [])
    n = c.try_nudge(now=_utc(2026, 5, 25))
    assert n is not None
    c.record_report(n.id, NudgeOutcome.DONE)
    c.adapt()
    new_program = store.get_program("u1")
    assert new_program.progression["squat_lb"] > starting_squat, (
        "Done report must progress the program — that's the difference between "
        "a coach and a plan generator (Rubric B3)."
    )


def test_program_deloads_after_two_partials(coach):
    c, store, cal, _ = coach
    c.record_intake({"experience": "novice", "days_per_week": "3"})
    _, _, _, program = c.build_program("strong + energetic")
    cal.seed("u1", [])
    start_load = program.progression["squat_lb"]
    for _ in range(2):
        n = c.try_nudge(now=_utc(2026, 5, 25) + timedelta(days=_*2))
        if n is None:
            # Force one through restraint by clearing.
            store.conn.execute("DELETE FROM nudges WHERE user_id='u1'"); store.conn.commit()
            n = c.try_nudge(now=_utc(2026, 5, 25) + timedelta(days=_*2))
        c.record_report(n.id, NudgeOutcome.PARTIAL, friction_note="last set failed")
        c.adapt()
    new_load = store.get_program("u1").progression["squat_lb"]
    assert new_load < start_load, "two partials in a row must trigger a deload"


# ---- Rubric A4 — loop closing -----------------------------------------------

def test_followup_appears_when_user_ignores(coach):
    c, store, cal, _ = coach
    c.record_intake({"experience": "novice", "days_per_week": "3"})
    c.build_program("strong + energetic")
    cal.seed("u1", [])
    n = c.try_nudge(now=_utc(2026, 5, 25, 9))
    assert n is not None
    # Past the fire window
    followups = c.open_followups(now=_utc(2026, 5, 26, 12))
    assert any("Earlier I asked" in f.prompt for f in followups)


# ---- Rubric B5 — safety -----------------------------------------------------

def test_safety_handoff_on_injury_signal(coach):
    c, store, _, _ = coach
    profile, handoff = c.record_intake({"injuries": "sharp pain in my lower back when I bend"})
    assert handoff is not None
    assert "physio" in handoff.lower() or "doctor" in handoff.lower()


def test_safety_handoff_on_mental_health_signal(coach):
    c, store, _, _ = coach
    _, handoff = c.record_intake({"experience": "I feel hopeless lately"})
    assert handoff is not None
    assert "988" in handoff or "helpline" in handoff.lower()
