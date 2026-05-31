"""APNs push wiring: store-backed tokens, ES256 signing, payload, 410 pruning."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from coach.models import Nudge
from coach.push import APNsPushDelivery, LoggingPushDelivery, make_push
from coach.store import Store


def _p8_pem() -> str:
    """A throwaway EC P-256 key in PKCS8 PEM — same shape as an Apple .p8."""
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def _nudge() -> Nudge:
    return Nudge(
        user_id="u1",
        action_id="a1",
        fire_window_until=datetime.now(timezone.utc) + timedelta(hours=2),
        headline="Squat day",
        body="5x5 at 135. Bar's waiting.",
        implementation_intention="After work, go straight to the rack.",
    )


class _StubResp:
    def __init__(self, status, body=None):
        self.status_code = status
        self._body = body or {}

    def json(self):
        return self._body


class _StubClient:
    """Stands in for the httpx HTTP/2 client — records calls, returns canned status."""
    def __init__(self, status=200, body=None):
        self.status = status
        self.body = body
        self.calls = []

    def post(self, path, json, headers):
        self.calls.append({"path": path, "json": json, "headers": headers})
        return _StubResp(self.status, self.body)


def _apns(store, client):
    return APNsPushDelivery(
        store=store, team_id="TEAMID123", key_id="KEYID456", key_p8=_p8_pem(),
        topic="ai.zaimler.TheCoach", sandbox=True, client=client,
    )


# ---- token persistence ------------------------------------------------------

def test_tokens_persist_in_store():
    store = Store(":memory:")
    store.save_push_token("u1", "dev-token-A")
    store.save_push_token("u1", "dev-token-A")  # idempotent
    store.save_push_token("u1", "dev-token-B")
    assert sorted(store.get_push_tokens("u1")) == ["dev-token-A", "dev-token-B"]
    store.delete_push_token("dev-token-A")
    assert store.get_push_tokens("u1") == ["dev-token-B"]


def test_register_device_writes_through_to_store():
    store = Store(":memory:")
    apns = _apns(store, _StubClient())
    apns.register_device("u1", "dev-token-C")
    assert store.get_push_tokens("u1") == ["dev-token-C"]


# ---- delivery ---------------------------------------------------------------

def test_deliver_posts_signed_alert_to_each_device():
    store = Store(":memory:")
    store.save_push_token("u1", "tok-XYZ")
    client = _StubClient(200)
    apns = _apns(store, client)

    apns.deliver(user_id="u1", nudge=_nudge())

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["path"] == "/3/device/tok-XYZ"
    assert call["headers"]["apns-topic"] == "ai.zaimler.TheCoach"
    assert call["headers"]["apns-push-type"] == "alert"
    # Payload carries the nudge for the app to render + deep-link the reply.
    assert call["json"]["aps"]["alert"]["title"] == "Squat day"
    assert call["json"]["action_id"] == "a1"
    # The auth header is a valid ES256 JWT with our key id + team as issuer.
    auth = call["headers"]["authorization"]
    assert auth.startswith("bearer ")
    token = auth.split(" ", 1)[1]
    assert jwt.get_unverified_header(token)["kid"] == "KEYID456"
    assert jwt.decode(token, options={"verify_signature": False})["iss"] == "TEAMID123"


def test_deliver_noop_without_tokens():
    store = Store(":memory:")
    client = _StubClient(200)
    apns = _apns(store, client)
    apns.deliver(user_id="u1", nudge=_nudge())
    assert client.calls == []


def test_410_prunes_dead_token():
    store = Store(":memory:")
    store.save_push_token("u1", "stale-tok")
    client = _StubClient(410, {"reason": "Unregistered"})
    apns = _apns(store, client)
    apns.deliver(user_id="u1", nudge=_nudge())
    assert store.get_push_tokens("u1") == []


def test_jwt_is_reused_across_calls():
    store = Store(":memory:")
    store.save_push_token("u1", "tok-1")
    client = _StubClient(200)
    apns = _apns(store, client)
    apns.deliver(user_id="u1", nudge=_nudge())
    apns.deliver(user_id="u1", nudge=_nudge())
    auths = {c["headers"]["authorization"] for c in client.calls}
    assert len(auths) == 1  # cached, not minted per request


# ---- factory ----------------------------------------------------------------

def test_make_push_defaults_to_logging(monkeypatch):
    for v in ("APNS_KEY_P8", "APNS_KEY_P8_FILE", "APNS_KEY_ID", "APNS_TEAM_ID", "APNS_TOPIC"):
        monkeypatch.delenv(v, raising=False)
    assert isinstance(make_push(Store(":memory:")), LoggingPushDelivery)


def test_make_push_selects_apns_when_configured(monkeypatch):
    monkeypatch.setenv("APNS_KEY_P8", _p8_pem())
    monkeypatch.setenv("APNS_KEY_ID", "KEYID456")
    monkeypatch.setenv("APNS_TEAM_ID", "TEAMID123")
    monkeypatch.setenv("APNS_TOPIC", "ai.zaimler.TheCoach")
    push = make_push(Store(":memory:"))
    assert isinstance(push, APNsPushDelivery)
