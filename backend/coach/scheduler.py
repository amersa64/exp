"""
Autonomous scheduler — the brain wakes itself and decides whether to nudge.

This is the dimension that separates a *library* from an *agent* (Rubric A2).
Without this loop, the spec's Principle 2.2 ("Initiative — it reaches out
first") is just talk. With it, the user never has to open the app.

Two surfaces:
  - run_tick(now) — pure: evaluate every active user once at this `now`.
    Used by tests and the CLI demo so we can fast-forward time deterministically.
  - run_forever(interval_seconds=300) — calls run_tick on a real clock.

Design notes:
  - Cheap to run, idempotent. The Coach's `try_nudge` already implements all
    the restraint logic (daily cap, cooldown, back-off) so calling it every
    5 minutes is safe — it'll just return None when there's nothing to do.
  - Sweeps ignored nudges on every tick so loop-closing followups stay fresh.
  - One Coach instance per user per tick. Cheap (Coach holds no request-state).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from .integrations import CalendarClient, HealthKitClient
from .lifecycle import Coach
from .llm import LLMClient
from .models import Nudge
from .push import PushDelivery
from .store import Store


log = logging.getLogger("coach.scheduler")


@dataclass
class TickResult:
    now: datetime
    users_evaluated: int
    nudges_fired: list[Nudge] = field(default_factory=list)
    followups_owed: int = 0
    silences: int = 0  # users where the engine deliberately chose not to nudge


class Scheduler:
    def __init__(
        self,
        store: Store,
        llm: LLMClient,
        calendar: CalendarClient,
        healthkit: HealthKitClient,
        push: PushDelivery,
        active_users: Callable[[], list[tuple[str, str]]],
        # ^ returns [(user_id, domain), ...] — pluggable; in v1 it reads from store
    ) -> None:
        self.store = store
        self.llm = llm
        self.calendar = calendar
        self.healthkit = healthkit
        self.push = push
        self.active_users = active_users
        self._stop = False

    def run_tick(self, now: datetime | None = None) -> TickResult:
        now = now or datetime.now(timezone.utc)
        result = TickResult(now=now, users_evaluated=0)
        for user_id, domain in self.active_users():
            result.users_evaluated += 1
            try:
                coach = Coach(user_id, domain, self.store, self.llm, self.calendar, self.healthkit)
                coach.nudge_engine.push = self.push  # share the transport

                # 1) Sweep ignored — keeps loop-closing followups honest.
                coach.nudge_engine.sweep_ignored(user_id, now)

                # 2) Decide & fire (or stay silent).
                n = coach.try_nudge(now=now)
                if n is None:
                    result.silences += 1
                else:
                    result.nudges_fired.append(n)

                # 3) Count followups so a monitor can show them.
                followups = coach.open_followups(now=now)
                result.followups_owed += len(followups)
            except Exception as exc:  # don't let one user's failure kill the tick
                log.exception("scheduler: user %s failed: %s", user_id, exc)
        return result

    def run_forever(self, interval_seconds: int = 300) -> None:  # pragma: no cover
        while not self._stop:
            self.run_tick()
            time.sleep(interval_seconds)

    def stop(self) -> None:
        self._stop = True


# ---------------------------------------------------------------------------
# A simple `active_users` source backed by the store. In production this
# might be a query over engaged users; v1 just returns every profiled user.
# ---------------------------------------------------------------------------

def active_users_from_store(store: Store) -> Callable[[], list[tuple[str, str]]]:
    def _query() -> list[tuple[str, str]]:
        rows = store.conn.execute(
            "SELECT user_id, json FROM profiles"
        ).fetchall()
        out: list[tuple[str, str]] = []
        from .models import UserProfile
        for user_id, blob in rows:
            try:
                p = UserProfile.model_validate_json(blob)
                out.append((user_id, p.domain))
            except Exception:
                continue
        return out
    return _query
