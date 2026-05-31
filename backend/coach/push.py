"""
Push delivery — the wire to the user's device (Section 8.3, Rubric A2).

Two implementations:
  - LoggingPushDelivery: in-process, prints/records what would have shipped.
                          Used in dev, tests, and the CLI demo.
  - APNsPushDelivery:    sketched. Needs an Apple Developer p8 key + topic.
                          Wired through the same interface so swapping is one line.

Why an interface and not "just send a notification": the brain must be testable
without a phone, and the push wire must be swappable (APNs, FCM, web push) without
touching the engine.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

from .models import Nudge


class PushDelivery(Protocol):
    def deliver(self, *, user_id: str, nudge: Nudge) -> str: ...
    def register_device(self, user_id: str, token: str, platform: str = "ios") -> None: ...


# ---------------------------------------------------------------------------

@dataclass
class _DeliveredRecord:
    user_id: str
    nudge_id: str
    body: str
    at: datetime


@dataclass
class LoggingPushDelivery:
    """In-process delivery — records what would have been pushed."""
    records: list[_DeliveredRecord] = field(default_factory=list)
    tokens: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    verbose: bool = False

    def register_device(self, user_id: str, token: str, platform: str = "ios") -> None:
        self.tokens.setdefault(user_id, []).append((platform, token))

    def deliver(self, *, user_id: str, nudge: Nudge) -> str:
        rec = _DeliveredRecord(user_id, nudge.id, nudge.body, nudge.fired_at)
        self.records.append(rec)
        if self.verbose:
            print(f"  [push] → {user_id}: {nudge.body}")
        return nudge.id


# ---------------------------------------------------------------------------

_APNS_PROD = "https://api.push.apple.com"
_APNS_SANDBOX = "https://api.sandbox.push.apple.com"
# APNs caps provider-token age at 1h; refresh comfortably inside that.
_JWT_TTL_SECONDS = 3000


class APNsPushDelivery:
    """
    Real APNs delivery: HTTP/2 to Apple with token-based (.p8) auth.

    Device tokens are read from and written to the store (not in-process) so
    push survives a stateless / scale-to-zero backend. A nudge is already
    persisted by the engine before we're called; this is purely the wire.

    The signing JWT (ES256, your .p8 key) is cached and reused — APNs throttles
    providers that mint a fresh token per request. On a 410 (Unregistered) or a
    400 bad-token reason we prune the dead token so we stop pushing to it.

    `client` is injectable for tests; in prod it's an httpx HTTP/2 client.
    """

    def __init__(
        self,
        *,
        store,
        team_id: str,
        key_id: str,
        key_p8: str,
        topic: str,
        sandbox: bool = True,
        client=None,
    ) -> None:
        self._store = store
        self.team_id = team_id
        self.key_id = key_id
        self.key_p8 = key_p8          # PEM contents of the AuthKey_*.p8
        self.topic = topic            # the app bundle id, e.g. ai.zaimler.TheCoach
        self.sandbox = sandbox
        self._log = logging.getLogger("coach.push")
        self._jwt: str | None = None
        self._jwt_at: float = 0.0
        if client is not None:
            self._client = client
        else:
            import httpx
            base = _APNS_SANDBOX if sandbox else _APNS_PROD
            self._client = httpx.Client(http2=True, base_url=base, timeout=10.0)

    # -- token registry (store-backed) --------------------------------------

    def register_device(self, user_id: str, token: str, platform: str = "ios") -> None:
        self._store.save_push_token(user_id, token, platform)

    # -- signing -------------------------------------------------------------

    def _auth_token(self) -> str:
        """Cached ES256 provider JWT, refreshed before APNs' 1h ceiling."""
        import time

        now = time.time()
        if self._jwt is None or (now - self._jwt_at) > _JWT_TTL_SECONDS:
            import jwt  # PyJWT (+ cryptography for ES256)

            self._jwt = jwt.encode(
                {"iss": self.team_id, "iat": int(now)},
                self.key_p8,
                algorithm="ES256",
                headers={"kid": self.key_id},
            )
            self._jwt_at = now
        return self._jwt

    # -- payload -------------------------------------------------------------

    def _payload(self, nudge: Nudge) -> dict:
        """APNs alert payload. Custom keys let the app deep-link the reply."""
        return {
            "aps": {
                "alert": {"title": nudge.headline, "body": nudge.body},
                "sound": "default",
            },
            "nudge_id": nudge.id,
            "action_id": nudge.action_id,
            "implementation_intention": nudge.implementation_intention or "",
        }

    # -- delivery ------------------------------------------------------------

    def deliver(self, *, user_id: str, nudge: Nudge) -> str:
        tokens = self._store.get_push_tokens(user_id)
        if not tokens:
            self._log.info("push: no device tokens for %s — skipping", user_id)
            return nudge.id
        payload = self._payload(nudge)
        auth = self._auth_token()
        for device in tokens:
            try:
                self._send(device, payload, auth)
            except Exception as exc:  # one dead device must not sink the rest
                self._log.warning("push: delivery to %s failed: %s", device[:8], exc)
        return nudge.id

    def _send(self, device_token: str, payload: dict, auth: str) -> None:
        resp = self._client.post(
            f"/3/device/{device_token}",
            json=payload,
            headers={
                "authorization": f"bearer {auth}",
                "apns-topic": self.topic,
                "apns-push-type": "alert",
                "apns-priority": "10",
            },
        )
        if resp.status_code == 200:
            return
        # 410 = token no longer valid; 400 BadDeviceToken/DeviceTokenNotForTopic.
        reason = ""
        try:
            reason = (resp.json() or {}).get("reason", "")
        except Exception:
            pass
        if resp.status_code == 410 or reason in {"BadDeviceToken", "Unregistered", "DeviceTokenNotForTopic"}:
            self._store.delete_push_token(device_token)
            self._log.info("push: pruned dead token %s… (%s)", device_token[:8], reason or resp.status_code)
        else:
            self._log.warning("push: APNs %s for %s… reason=%s", resp.status_code, device_token[:8], reason)


def make_push(store):
    """Pick the push transport from the environment.

    Returns an APNsPushDelivery when the APNs credentials are present, else the
    in-process LoggingPushDelivery (dev / tests / CLI). The .p8 key may be given
    inline as APNS_KEY_P8 or as a path in APNS_KEY_P8_FILE.
    """
    import os

    key_p8 = os.environ.get("APNS_KEY_P8")
    key_file = os.environ.get("APNS_KEY_P8_FILE")
    if not key_p8 and key_file:
        try:
            key_p8 = Path(key_file).read_text()
        except OSError:
            key_p8 = None
    key_id = os.environ.get("APNS_KEY_ID")
    team_id = os.environ.get("APNS_TEAM_ID")
    topic = os.environ.get("APNS_TOPIC")

    if key_p8 and key_id and team_id and topic:
        sandbox = os.environ.get("APNS_SANDBOX", "true").lower() not in {"0", "false", "no"}
        return APNsPushDelivery(
            store=store, team_id=team_id, key_id=key_id, key_p8=key_p8,
            topic=topic, sandbox=sandbox,
        )
    return LoggingPushDelivery()
