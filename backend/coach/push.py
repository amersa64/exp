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

from dataclasses import dataclass, field
from datetime import datetime
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

class APNsPushDelivery:
    """
    SCAFFOLD. Real APNs delivery via HTTP/2 with token-based auth (.p8 key).

    Wiring: this would use `httpx` against api.push.apple.com with a JWT signed
    by your APNs key. Not built here because:
      - it needs an Apple Developer team_id + key_id + .p8 (not in repo)
      - sandbox vs prod topic switching is environment-specific
      - it's a thin, well-documented adapter — drop it in once creds exist
    """

    def __init__(self, *, team_id: str, key_id: str, key_pem: str, topic: str, sandbox: bool = True) -> None:
        self.team_id = team_id
        self.key_id = key_id
        self.key_pem = key_pem
        self.topic = topic
        self.sandbox = sandbox
        self.tokens: dict[str, list[str]] = {}

    def register_device(self, user_id: str, token: str, platform: str = "ios") -> None:
        self.tokens.setdefault(user_id, []).append(token)

    def deliver(self, *, user_id: str, nudge: Nudge) -> str:  # pragma: no cover
        raise NotImplementedError(
            "APNs delivery not implemented in this build. Plug in here using your "
            "p8 key + httpx HTTP/2. The nudge is already persisted; this is the wire."
        )
