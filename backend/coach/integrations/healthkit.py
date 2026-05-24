"""
HealthKit interface (Section 8.1) — used for BOTH timing context AND verification.

On-device, the iOS client reads HealthKit and POSTs signals to the backend.
Backend code talks only to this interface so the nudge engine and verification
path are testable without a device.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol


@dataclass
class HealthSignal:
    user_id: str
    kind: str            # "steps", "workout", "sleep", "active_energy"
    at: datetime
    value: float
    metadata: dict[str, str] = field(default_factory=dict)


class HealthKitClient(Protocol):
    def recent_signals(self, user_id: str, since: datetime) -> list[HealthSignal]: ...
    def workout_occurred(self, user_id: str, around: datetime, window_minutes: int = 90) -> HealthSignal | None: ...


@dataclass
class StubHealthKitClient:
    signals: dict[str, list[HealthSignal]] = field(default_factory=dict)

    def seed(self, sig: HealthSignal) -> None:
        self.signals.setdefault(sig.user_id, []).append(sig)

    def recent_signals(self, user_id: str, since: datetime) -> list[HealthSignal]:
        return [s for s in self.signals.get(user_id, []) if s.at >= since]

    def workout_occurred(self, user_id: str, around: datetime, window_minutes: int = 90) -> HealthSignal | None:
        lo = around - timedelta(minutes=window_minutes)
        hi = around + timedelta(minutes=window_minutes)
        for s in self.signals.get(user_id, []):
            if s.kind == "workout" and lo <= s.at <= hi:
                return s
        return None
