"""
Seed realistic demo data for the iOS app.

Honors the mirror principle: WorldState.grow() is only called with real
VerifiedEvents constructed against real prescribed AtomicActions. Events
are backdated so the streak compounds across days.

Usage:  .venv/bin/python -m cli.seed_demo_data
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from coach.integrations import StubCalendarClient, StubHealthKitClient
from coach.lifecycle import Coach
from coach.llm import LLMClient
from coach.models import (
    AtomicAction,
    NudgeOutcome,
    VerifiedEvent,
    WorldState,
)
from coach.push import LoggingPushDelivery
from coach.store import Store


USER_ID = "demo-user"
DOMAIN = "fitness"
DB_PATH = "coach.db"

# Use a date a couple weeks ago so the seeded "today" is recent.
END_DATE = datetime.now(timezone.utc).replace(hour=9, minute=0, second=0, microsecond=0)


def _coach() -> Coach:
    return Coach(
        USER_ID, DOMAIN, Store(DB_PATH), LLMClient(),
        StubCalendarClient(), StubHealthKitClient(),
    )


def _ensure_intake_and_program(coach: Coach) -> AtomicAction:
    if coach.store.get_profile(USER_ID) is None:
        coach.record_intake({
            "experience": "novice — been to a gym, never on a real program",
            "days_per_week": "3",
            "injuries": "none",
            "equipment": "barbell + rack at home",
            "baseline_squat": "135",
        })
    if coach.store.get_program(USER_ID) is None:
        coach.build_program("Someone who shows up, even on hard days.")
    action, _ = coach.prepare_next_action()
    return action


def _backdated_verification(coach: Coach, action: AtomicAction, at: datetime) -> None:
    """Construct a VerifiedEvent at a specific past timestamp and grow the world."""
    event = VerifiedEvent(
        user_id=USER_ID,
        action_id=action.id,
        nudge_id=None,
        source="sensor",
        sensor="healthkit.workout",
        at=at,
        payload={"duration_min": 45},
    )
    coach.store.save_verified_event(event)
    world = coach.store.get_world(USER_ID) or WorldState(
        user_id=USER_ID, theme=coach.persona.world_theme
    )
    world.grow(event, action)
    coach.store.save_world(world, growth_event=event)


def main() -> int:
    coach = _coach()
    coach.nudge_engine.push = LoggingPushDelivery()
    action = _ensure_intake_and_program(coach)

    # Build a consecutive-day streak ending today. 12 consecutive days so
    # streak shows 12 and currency lands around 120 (sensor source = +10).
    streak_days = 12
    for offset in range(streak_days, 0, -1):
        when = END_DATE - timedelta(days=offset - 1)
        _backdated_verification(coach, action, when)

    # Mark one nudge as PENDING with an expired fire time so Today shows a
    # genuine open follow-up.
    open_when = END_DATE + timedelta(hours=1)
    nudge = coach.try_nudge(now=open_when)
    if nudge is not None:
        coach.nudge_engine.sweep_ignored(USER_ID, open_when + timedelta(hours=4))

    world = coach.store.get_world(USER_ID)
    print(f"World: currency={world.currency}, streak={world.streak_days}, "
          f"longest={world.longest_streak}, theme={world.theme}")
    print(f"Living systems: {world.living_systems}")
    print(f"Nudges in DB: {len(coach.store.recent_nudges(USER_ID, limit=50))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
