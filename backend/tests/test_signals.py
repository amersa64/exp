"""HTTP tests for the iPhone-signals surface (Section 8.1)."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DB", str(tmp_path / "coach.db"))
    if "api.app" in sys.modules:
        del sys.modules["api.app"]
    from api.app import app
    with TestClient(app) as c:
        yield c


def _onboard(client, user="alice"):
    headers = {"X-User-Id": user}
    client.post("/intake/submit", json={
        "answers": {"experience": "novice", "days_per_week": "3", "injuries": "none"},
        "identity_statement": "strong + energetic",
    }, headers=headers)
    return headers


# ---- Feature 1: Readiness Engine -------------------------------------------

def test_readiness_low_score_drives_rest_directive(client):
    headers = _onboard(client)
    r = client.post("/signals/readiness", json={
        "sleep_hours": 3.5, "resting_hr": 72,
        "resting_hr_baseline": 55, "hrv_ms": 28, "hrv_baseline": 60,
    }, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["band"] == "rest"
    assert body["directive"] == "rest"
    assert body["note"] and "Readiness" in body["note"]


def test_readiness_surfaces_in_session_next(client):
    headers = _onboard(client)
    client.post("/signals/readiness", json={
        "sleep_hours": 8.0, "resting_hr": 50,
        "resting_hr_baseline": 55, "hrv_ms": 68, "hrv_baseline": 60,
    }, headers=headers)
    r = client.get("/session/next", headers=headers)
    assert r.status_code == 200
    readiness = r.json()["readiness"]
    assert readiness is not None
    assert readiness["band"] == "primed"
    assert readiness["directive"] == "full"


def test_session_next_has_no_readiness_before_signal(client):
    headers = _onboard(client)
    r = client.get("/session/next", headers=headers)
    assert r.status_code == 200
    assert r.json()["readiness"] is None


# ---- Feature 2: Gym Radar --------------------------------------------------

def test_place_learns_and_becomes_monitorable(client):
    headers = _onboard(client)
    last = None
    for _ in range(3):
        r = client.post("/signals/place/observe",
                        json={"lat": 37.7749, "lon": -122.4194}, headers=headers)
        assert r.status_code == 200
        last = r.json()
    assert last["monitorable"] is True
    assert last["confidence"] >= 0.5

    # GET reflects the learned place.
    r = client.get("/signals/place", headers=headers)
    assert r.json()["monitorable"] is True


def test_arrival_surfaces_session(client):
    headers = _onboard(client)
    client.post("/signals/place/observe",
                json={"lat": 37.7749, "lon": -122.4194}, headers=headers)
    r = client.post("/signals/location-event",
                    json={"event": "arrived"}, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["surface_session"] is True
    assert body["coach_line"]


# ---- Feature 3: Auto-log from Apple Health ---------------------------------

def test_autolog_grows_world_from_sensor(client):
    headers = _onboard(client)
    action_id = client.get("/session/next", headers=headers).json()["action_id"]

    before = client.get("/world", headers=headers).json()["currency"]
    r = client.post(f"/session/{action_id}/autolog", json={
        "duration_min": 47, "active_kcal": 320, "avg_hr": 138,
        "workout_type": "functionalStrengthTraining",
    }, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["outcome"] == "done"
    assert body["ripples"]  # world grew

    after = client.get("/world", headers=headers).json()
    # Sensor verifications are worth +10 effort (vs +7 for a self-report).
    assert after["currency"] == before + 10
    assert after["identity_votes"] >= 1


def test_autolog_unknown_action_404(client):
    headers = _onboard(client)
    r = client.post("/session/nope/autolog", json={"duration_min": 30}, headers=headers)
    assert r.status_code == 404
