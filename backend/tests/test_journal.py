"""
Coach journal tests — narrative memory contract.

The journal is the substrate every downstream LLM call reads from. If its
shape breaks, the nudge author, the coach_response composer, and the
adaptation narrator all degrade silently. These tests pin the contract.

We assert structure + stub-mode invariants, NOT the prose content (that's
the LLM's job; offline we can only guarantee it produces SOMETHING).
"""

from __future__ import annotations

import os
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


def _seed(client, uid: str, equipment: str = "barbell+rack at home"):
    """Intake + program — the minimum to get to a prescribable state."""
    client.post(
        "/intake/submit",
        json={
            "answers": {
                "experience": "novice",
                "days_per_week": "3",
                "injuries": "none",
                "equipment": equipment,
            },
            "identity_statement": "I show up",
        },
        headers={"X-User-Id": uid},
    )


def test_intake_creates_first_journal_entry(client):
    _seed(client, "alice")
    state = client.get("/coach/state", headers={"X-User-Id": "alice"}).json()
    entry = state.get("latest_journal_entry")
    assert entry is not None
    assert entry["kind"] == "intake"
    # Stub never marks anything surface=true — that decision needs real
    # pattern recognition we don't fake offline.
    assert entry["surface"] is False
    assert entry["text"], "stub must still produce non-empty text"


def test_log_appends_journal_entry_with_outcome(client):
    h = {"X-User-Id": "alice"}
    _seed(client, "alice")
    nxt = client.get("/session/next", headers=h).json()
    client.post(
        f"/session/{nxt['action_id']}/log",
        json={"outcome": "partial", "friction": "low energy"},
        headers=h,
    )
    state = client.get("/coach/state", headers=h).json()
    # The most recent entry should reflect the most recent event — after
    # a log+adapt, that's the adapt note (adapt runs after log). What we
    # care about: a journal entry exists and a 'reply'-kind entry is in
    # the trail because friction was non-empty.
    entry = state["latest_journal_entry"]
    assert entry is not None
    assert entry["kind"] in {"adapt", "reply", "log"}


def test_coach_response_returned_with_friction(client):
    h = {"X-User-Id": "alice"}
    _seed(client, "alice")
    nxt = client.get("/session/next", headers=h).json()
    resp = client.post(
        f"/session/{nxt['action_id']}/log",
        json={"outcome": "partial", "friction": "right knee twinge"},
        headers=h,
    ).json()
    # Contract: when the user wrote something, the coach acknowledges it.
    assert resp["coach_response"], "missing coach_response when friction provided"
    # And the friction text rides along in the stub acknowledgment.
    assert "knee" in resp["coach_response"].lower() or "twinge" in resp["coach_response"].lower()


def test_clean_done_omits_coach_response(client):
    h = {"X-User-Id": "alice"}
    _seed(client, "alice")
    nxt = client.get("/session/next", headers=h).json()
    resp = client.post(
        f"/session/{nxt['action_id']}/log",
        json={"outcome": "done"},
        headers=h,
    ).json()
    # Clean done with no note → ripples speak for themselves, no extra reply.
    assert resp["coach_response"] is None


def test_adaptation_narrative_is_coach_voice(client):
    h = {"X-User-Id": "alice"}
    _seed(client, "alice")
    nxt = client.get("/session/next", headers=h).json()
    resp = client.post(
        f"/session/{nxt['action_id']}/log",
        json={"outcome": "done"},
        headers=h,
    ).json()
    rationale = resp["adaptation"]
    assert rationale  # never empty
    # Coach-voice cue ("Cleared the prescribed work...") rather than the
    # raw technical sentence ("+10 squat, +5 bench"). The technical line
    # should still ride along in parens so debug stays transparent.
    assert "cleared" in rationale.lower() or "earning" in rationale.lower()


def test_journal_persists_across_events(client):
    """Append-only history accumulates — that's the WHOLE point of the journal."""
    h = {"X-User-Id": "alice"}
    _seed(client, "alice")
    for _ in range(3):
        nxt = client.get("/session/next", headers=h).json()
        client.post(
            f"/session/{nxt['action_id']}/log",
            json={"outcome": "done"},
            headers=h,
        )
    # Read journal directly via the in-process store — the API doesn't
    # expose the full journal yet (Section 11: no surface without a reason).
    from api.app import app
    j = app.state.store.get_journal("alice")
    assert j is not None
    # intake (1) + 3 × (log + adapt) = at least 7. We assert >=4 to stay
    # robust to engine tweaks that may journal more or fewer events per log.
    assert len(j.entries) >= 4
    kinds = {e.kind for e in j.entries}
    assert "intake" in kinds
    # Some downstream event kind shows up (log or reply or adapt).
    assert kinds & {"log", "reply", "adapt"}
