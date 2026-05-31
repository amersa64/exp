"""Auth gate: bearer-token enforcement + /dev/* gating (see _auth_gate in app.py)."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_TOKEN = "test-secret-token"


def _client(tmp_path, monkeypatch, *, token=None, enable_dev=None):
    """Build a TestClient with the auth env applied. Force-reimports api.app so
    its module-level auth constants (API_TOKEN, DEV_ENABLED) re-read the env."""
    monkeypatch.setenv("COACH_DB", str(tmp_path / "coach.db"))
    if token is None:
        monkeypatch.delenv("COACH_API_TOKEN", raising=False)
    else:
        monkeypatch.setenv("COACH_API_TOKEN", token)
    if enable_dev is None:
        monkeypatch.delenv("COACH_ENABLE_DEV", raising=False)
    else:
        monkeypatch.setenv("COACH_ENABLE_DEV", enable_dev)
    if "api.app" in sys.modules:
        del sys.modules["api.app"]
    from api.app import app
    return TestClient(app)


# ---- open mode (no token) — local/test default -----------------------------

def test_open_mode_allows_unauthenticated(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, token=None) as c:
        assert c.get("/healthz").status_code == 200
        # Protected route reachable with only the identity header, no bearer.
        assert c.get("/intake/questions", headers={"X-User-Id": "u1"}).status_code == 200


def test_open_mode_enables_dev_routes(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, token=None) as c:
        assert c.get("/dev/scenarios").status_code == 200


# ---- hardened mode (token set) ----------------------------------------------

def test_healthz_public_even_with_token(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, token=_TOKEN) as c:
        assert c.get("/healthz").status_code == 200  # no bearer needed


def test_missing_token_rejected(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, token=_TOKEN) as c:
        r = c.get("/intake/questions", headers={"X-User-Id": "u1"})
        assert r.status_code == 401


def test_wrong_token_rejected(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, token=_TOKEN) as c:
        r = c.get("/intake/questions",
                  headers={"X-User-Id": "u1", "Authorization": "Bearer nope"})
        assert r.status_code == 401


def test_correct_token_accepted(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, token=_TOKEN) as c:
        r = c.get("/intake/questions",
                  headers={"X-User-Id": "u1", "Authorization": f"Bearer {_TOKEN}"})
        assert r.status_code == 200


def test_dev_routes_hidden_when_hardened(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, token=_TOKEN) as c:
        # 404 (not 401/403) so a deployed box doesn't even advertise /dev/*.
        r = c.get("/dev/scenarios", headers={"Authorization": f"Bearer {_TOKEN}"})
        assert r.status_code == 404


def test_dev_routes_reopenable_with_flag(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, token=_TOKEN, enable_dev="1") as c:
        # Still requires the bearer token, but the route is reachable again.
        assert c.get("/dev/scenarios").status_code == 401
        r = c.get("/dev/scenarios", headers={"Authorization": f"Bearer {_TOKEN}"})
        assert r.status_code == 200
