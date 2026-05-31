"""
Parity tests: the brain must behave identically on PgStore (Postgres/Supabase)
as it does on the SQLite Store. We don't re-test coaching logic here — we run
the load-bearing lifecycle paths through a real Postgres connection so any
dialect or serialization drift in pg_store.py surfaces immediately.

Gated on PG_TEST_DSN so it's a no-op for anyone without a Postgres handy:

    PG_TEST_DSN=postgresql:///coach_pg_test python -m pytest backend/tests/test_pg_store.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from coach.integrations import HealthSignal, StubCalendarClient, StubHealthKitClient
from coach.lifecycle import Coach
from coach.llm import LLMClient
from coach.models import NudgeOutcome, VitalSample

_DSN = os.environ.get("PG_TEST_DSN")
pytestmark = pytest.mark.skipif(not _DSN, reason="set PG_TEST_DSN to run Postgres parity tests")


def _utc(y, m, d, h=9, mn=0):
    return datetime(y, m, d, h, mn, tzinfo=timezone.utc)


@pytest.fixture
def pg_coach():
    from coach.pg_store import PgStore

    store = PgStore(_DSN)
    # Clean slate — these tests own the database.
    with store.pool.connection() as conn:
        for t in (
            "identities", "milestones", "habits", "actions", "profiles",
            "programs", "world", "nudges", "verified_events", "journals",
            "ai_programs", "adjustments", "readiness", "places", "vitals",
        ):
            conn.execute(f"DELETE FROM {t}")
    cal = StubCalendarClient()
    hk = StubHealthKitClient()
    c = Coach("u1", "fitness", store, LLMClient(), cal, hk)
    try:
        yield c, store, cal, hk
    finally:
        store.close()


def test_pg_mirror_integrity_rejects_unverified_growth(pg_coach):
    c, store, _, _ = pg_coach
    c.record_intake({"experience": "novice", "days_per_week": "3"})
    c.build_program("strong + energetic")
    w = store.get_world("u1")
    assert w is not None
    w.currency += 1_000_000
    with pytest.raises(PermissionError):
        store.save_world(w)  # no growth_event → must reject, same as SQLite


def test_pg_world_grows_from_report(pg_coach):
    c, store, cal, _ = pg_coach
    c.record_intake({"experience": "novice", "days_per_week": "3"})
    c.build_program("strong + energetic")
    cal.seed("u1", [])
    n = c.try_nudge(now=_utc(2026, 5, 25))
    assert n is not None
    _, ripples, _ = c.record_report(n.id, NudgeOutcome.DONE)
    assert ripples
    assert store.get_world("u1").currency > 0


def test_pg_persistence_across_instances(pg_coach):
    c, store, _, _ = pg_coach
    c.record_intake({"experience": "novice", "days_per_week": "3"})
    c.build_program("strong + energetic")

    from coach.pg_store import PgStore
    s2 = PgStore(_DSN)
    try:
        assert s2.get_profile("u1") is not None
        assert s2.get_program("u1") is not None
    finally:
        s2.close()


def test_pg_vitals_roundtrip_and_idempotency(pg_coach):
    _, store, _, _ = pg_coach
    t = _utc(2026, 5, 25, 7)
    store.save_vital_samples("u1", [VitalSample(metric="hrv", at=t, value=42.0, unit="ms")])
    # Re-post the same (metric, at) with a new value → upsert, not duplicate.
    store.save_vital_samples("u1", [VitalSample(metric="hrv", at=t, value=55.0, unit="ms")])
    series = store.vitals_series("u1", "hrv")
    assert len(series) == 1
    assert series[0].value == 55.0
    assert store.latest_vital("u1", "hrv").value == 55.0
    assert store.vitals_metrics("u1") == ["hrv"]


def test_pg_active_users_source(pg_coach):
    # Regression: active_users_from_store must not reach into store.conn (a
    # SQLite-only attribute) — it has to work on PgStore too. This is the path
    # the scheduler tick runs on every cron heartbeat.
    from coach.scheduler import active_users_from_store

    c, store, _, _ = pg_coach
    c.record_intake({"experience": "novice", "days_per_week": "3"})
    c.build_program("strong + energetic")
    users = active_users_from_store(store)()
    assert ("u1", "fitness") in users


def test_pg_push_tokens_roundtrip(pg_coach):
    _, store, _, _ = pg_coach
    store.save_push_token("u1", "tok-A")
    store.save_push_token("u1", "tok-A")  # idempotent upsert
    store.save_push_token("u1", "tok-B")
    assert sorted(store.get_push_tokens("u1")) == ["tok-A", "tok-B"]
    store.delete_push_token("tok-A")
    assert store.get_push_tokens("u1") == ["tok-B"]


def test_pg_wipe_user(pg_coach):
    c, store, _, _ = pg_coach
    c.record_intake({"experience": "novice", "days_per_week": "3"})
    c.build_program("strong + energetic")
    assert store.get_profile("u1") is not None
    store.wipe_user("u1")
    assert store.get_profile("u1") is None
    assert store.get_program("u1") is None
    assert store.get_world("u1") is None
    assert store.get_identity_for_user("u1") is None
