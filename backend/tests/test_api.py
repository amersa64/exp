"""HTTP layer smoke tests."""

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


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

    # 4. Trigger a scheduler tick — should fire a nudge
    r = client.post("/scheduler/tick")
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
    assert "completed" in body["adaptation"].lower() or "squat" in body["adaptation"].lower()

    # 6. World reflects growth
    r = client.get("/world", headers=headers)
    assert r.json()["currency"] > 0


def test_safety_handoff_via_api(client):
    headers = {"X-User-Id": "bob"}
    r = client.post("/intake/submit", json={
        "answers": {"injuries": "sharp pain shooting down my leg"},
    }, headers=headers)
    assert r.status_code == 200
    assert r.json()["handoff"] is not None
