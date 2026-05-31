"""HTTP layer smoke tests."""

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.conftest import session_log_body


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DB", str(tmp_path / "coach.db"))
    # Force re-import so the lifespan uses the fresh DB path.
    if "api.app" in sys.modules:
        del sys.modules["api.app"]
    from api.app import app
    with TestClient(app) as c:
        yield c


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_full_flow(client):
    headers = {"X-User-Id": "alice"}
    # 1. Intake questions
    r = client.get("/intake/questions", headers=headers)
    assert r.status_code == 200
    assert len(r.json()["questions"]) >= 3

    # 2. Submit intake + build program in one shot
    r = client.post("/intake/submit", json={
        "answers": {"experience": "novice", "days_per_week": "3", "injuries": "none"},
        "identity_statement": "strong + energetic",
    }, headers=headers)
    assert r.status_code == 200
    assert r.json()["program_built"] is True

    # 3. World now exists
    r = client.get("/world", headers=headers)
    assert r.status_code == 200
    assert r.json()["currency"] == 0  # not yet earned anything

    # 4. Trigger a scheduler tick — should fire a nudge.
    # Pin time to a mid-morning UTC moment so the calendar-window logic
    # inside the nudge engine has a real slot to schedule against,
    # regardless of when the test actually runs.
    r = client.post("/scheduler/tick?now=2026-06-15T10:00:00%2B00:00")
    assert r.status_code == 200
    fired = r.json()["nudges_fired"]
    assert len(fired) == 1

    # 5. Reply done — world should grow + program should adapt
    nudge_id = fired[0]
    r = client.post(f"/nudge/{nudge_id}/reply",
                    json={"outcome": "done", "friction": None}, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["ripples"]
    # Strength now starts in CALIBRATION phase; the first session is
    # Calibration 1 of 5. The adapt narrative for a calibration log talks
    # about "calibration" rather than the load deltas of a finished active
    # session. World growth still happens (a "done" report is a verified event).
    adaptation = body["adaptation"].lower()
    assert "calibration" in adaptation or "completed" in adaptation

    # 6. World reflects growth
    r = client.get("/world", headers=headers)
    assert r.json()["currency"] > 0


def test_identity_and_milestones_after_program(client):
    """Rubric E2 — the four-level hierarchy must be reflectable to the client
    so WorldView can render the user's actual identity statement and the real
    milestones from their program, not hardcoded strings."""
    headers = {"X-User-Id": "carol"}
    # No identity / milestones yet.
    assert client.get("/identity", headers=headers).status_code == 404
    assert client.get("/milestones", headers=headers).json() == {"milestones": []}

    client.post("/intake/submit", json={
        "answers": {"experience": "novice", "days_per_week": "3", "injuries": "none"},
        "identity_statement": "I am someone who shows up",
    }, headers=headers)

    r = client.get("/identity", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["statement"] == "I am someone who shows up"
    assert body["domain"] == "strength"  # v2: default goal-less intake routes to strength
    assert body["user_id"] == "carol"

    r = client.get("/milestones", headers=headers)
    assert r.status_code == 200
    ms = r.json()["milestones"]
    assert len(ms) >= 1
    # Every milestone must trace back to this user's identity (mirror integrity).
    ident_id = body["id"]
    assert all(m["parent_identity_id"] == ident_id for m in ms)


def test_session_endpoints_close_the_loop_without_apns(client):
    """The in-app path: get next session → log done → world grows + program adapts.

    Without this path the user is stranded on a blank Summit after intake when
    APNs is not configured. See Rubric C1.
    """
    headers = {"X-User-Id": "dora"}
    client.post("/intake/submit", json={
        "answers": {"experience": "novice", "days_per_week": "3", "injuries": "none"},
        "identity_statement": "consistent",
    }, headers=headers)

    r = client.get("/session/next", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["action_id"]
    assert body["session"]["exercises"], "session must carry specific exercises (Rubric B2)"

    action_id = body["action_id"]
    r = client.post(f"/session/{action_id}/log",
                    json=session_log_body(body, "done"), headers=headers)
    assert r.status_code == 200
    assert r.json()["ripples"], "completing a session must grow the world"

    assert client.get("/world", headers=headers).json()["currency"] > 0


def test_session_log_unknown_action(client):
    headers = {"X-User-Id": "erin"}
    client.post("/intake/submit", json={
        "answers": {"experience": "novice", "days_per_week": "3", "injuries": "none"},
        "identity_statement": "consistent",
    }, headers=headers)
    # Body shape must be valid (per-exercise dict) — we want to exercise the
    # 404 unknown-action path, not pydantic's 422. A single fake exercise
    # entry is enough; the action_id lookup fails first.
    r = client.post(
        "/session/does-not-exist/log",
        json={"exercises": {"Back Squat": {"outcome": "done"}}},
        headers=headers,
    )
    assert r.status_code == 404


def test_safety_handoff_via_api(client):
    headers = {"X-User-Id": "bob"}
    r = client.post("/intake/submit", json={
        "answers": {"injuries": "sharp pain shooting down my leg"},
    }, headers=headers)
    assert r.status_code == 200
    assert r.json()["handoff"] is not None


def test_exercise_swap_chosen_skips_llm(client):
    """A default-pick swap (explicit `chosen`) applies + remembers without
    invoking the LLM picker — the decision is already made client-side."""
    headers = {"X-User-Id": "carol"}
    client.post("/intake/submit", json={
        "answers": {"experience": "novice", "days_per_week": "3", "injuries": "none",
                    "equipment": "full gym"},
        "identity_statement": "strong",
    }, headers=headers)
    # Pick a real catalog exercise to swap and a real alternate to swap to.
    alts = client.get("/exercises/alternates", params={"name": "Barbell Squat"},
                      headers=headers)
    assert alts.status_code == 200
    candidates = alts.json()["alternates"]
    if not candidates:
        pytest.skip("no equipment-matched alternates for the seed exercise")
    chosen = candidates[0]["name"]

    r = client.post("/exercise/swap", json={
        "exercise_name": "Barbell Squat", "chosen": chosen,
    }, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["replacement"] == chosen
    # The swap is remembered as a standing constraint (coach memory).
    adj = client.get("/adjustments", headers=headers).json()["adjustments"]
    assert any(a["replacement_exercise"] == chosen for a in adj)


def test_exercise_swap_chosen_unknown_404(client):
    headers = {"X-User-Id": "dave"}
    client.post("/intake/submit", json={
        "answers": {"experience": "novice", "days_per_week": "3"},
        "identity_statement": "strong",
    }, headers=headers)
    r = client.post("/exercise/swap", json={
        "exercise_name": "Barbell Squat", "chosen": "Not A Real Exercise",
    }, headers=headers)
    assert r.status_code == 404
