"""The v2 Coach-tab shape engine: Prescription / Slip / Return / Pause."""

import sys
from datetime import datetime, timedelta, timezone
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
        "identity_statement": "strong + steady",
    }, headers=headers)
    return headers


def test_fresh_user_gets_prescription(client):
    headers = _onboard(client)
    r = client.get("/coach/today", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["shape"] == "prescription"
    assert body["coach_line"]
    assert body["action_id"]


def test_two_misses_triggers_slip(client):
    headers = _onboard(client)
    # Log two skipped sessions in a row.
    for _ in range(2):
        aid = client.get("/session/next", headers=headers).json()["action_id"]
        client.post(f"/session/{aid}/log",
                    json={"exercises": {"x": {"outcome": "skipped"}}, "friction": ""},
                    headers=headers)
    body = client.get("/coach/today", headers=headers).json()
    assert body["shape"] == "slip"
    assert "Two in a row" in body["coach_line"]


def test_done_breaks_the_slip(client):
    headers = _onboard(client)
    for _ in range(2):
        aid = client.get("/session/next", headers=headers).json()["action_id"]
        client.post(f"/session/{aid}/log",
                    json={"exercises": {"x": {"outcome": "skipped"}}, "friction": ""},
                    headers=headers)
    # A done session should reset the slip run.
    aid = client.get("/session/next", headers=headers).json()["action_id"]
    next_session = client.get("/session/next", headers=headers).json()
    body = {"exercises": {ex["name"]: {"outcome": "done"}
                          for ex in next_session["session"]["exercises"]}, "friction": ""}
    client.post(f"/session/{next_session['action_id']}/log", json=body, headers=headers)
    today = client.get("/coach/today", headers=headers).json()
    assert today["shape"] != "slip"


def test_pause_renders_pause_shape_and_silences_nudges(client):
    headers = _onboard(client)
    r = client.post("/program/pause", json={"days": 7}, headers=headers)
    assert r.status_code == 200
    today = client.get("/coach/today", headers=headers).json()
    assert today["shape"] == "pause"
    assert "Paused" in today["coach_line"]
    # A scheduler tick should not fire while paused.
    tick = client.post("/dev/tick", headers=headers).json()
    assert tick["fired"] is False
    # Resume restores a normal shape.
    client.post("/program/resume", headers=headers)
    assert client.get("/coach/today", headers=headers).json()["shape"] != "pause"


def test_return_after_absence(client):
    headers = _onboard(client, user="lapsed")
    # Seed one verified event 6 days ago by auto-logging, then backdate it.
    aid = client.get("/session/next", headers=headers).json()["action_id"]
    client.post(f"/session/{aid}/autolog", json={"duration_min": 30}, headers=headers)
    # Reach into the store to age the event (no API for time travel).
    from api.app import app
    store = app.state.store
    evs = store.verified_events_for("lapsed")
    evs[-1].at = datetime.now(timezone.utc) - timedelta(days=6)
    store.save_verified_event(evs[-1])
    body = client.get("/coach/today", headers=headers).json()
    assert body["shape"] == "return"
    assert body["days_away"] >= 5
