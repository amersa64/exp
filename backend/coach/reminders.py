"""
Weekly local-notification plan (Section 7, the free path to push).

The JITAI nudge engine decides timing dynamically at fire time from the
calendar + HealthKit — that can't be pre-scheduled days ahead, and real APNs
push needs a paid Apple account. Local notifications don't: the iOS client
schedules these as repeating calendar triggers in the device's local time, so
the user gets reminders around training even with a free/personal signing team.

This module turns the user's training cadence (days_per_week) into a small,
deterministic set of weekly recurring reminders: the night before, at training
time, and a post-session "log it" nudge — exactly the rhythm the user asked
for. Text is templated (not LLM-authored) on purpose: it's scheduled a week out
and must be cheap + stable. The dynamic, conditioned nudges stay on the APNs
path for when push is available.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

# How to spread N sessions/week across weekdays. Lowercase 3-letter codes; the
# iOS scheduler maps these to local calendar weekdays.
_DAY_SPREAD: dict[int, list[str]] = {
    1: ["wed"],
    2: ["mon", "thu"],
    3: ["mon", "wed", "fri"],
    4: ["mon", "tue", "thu", "fri"],
    5: ["mon", "tue", "wed", "thu", "fri"],
    6: ["mon", "tue", "wed", "thu", "fri", "sat"],
    7: ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
}

_PREV_DAY = {
    "mon": "sun", "tue": "mon", "wed": "tue", "thu": "wed",
    "fri": "thu", "sat": "fri", "sun": "sat",
}


@dataclass
class Reminder:
    id: str          # stable per slot — the client uses it to de-dupe on refresh
    weekday: str     # "mon".."sun"
    hour: int        # local wall-clock hour (0-23)
    minute: int
    title: str
    body: str


def weekly_reminder_plan(
    *,
    days_per_week: int,
    identity_statement: str | None = None,
    hour: int = 17,
    post_offset_min: int = 90,
) -> list[Reminder]:
    """Three reminders per training day: night-before, at-time, post-session.

    `hour` is the assumed training time (local). `post_offset_min` is how long
    after that to nudge a session log. Times that spill past midnight are
    dropped rather than bled into the next day.
    """
    n = max(1, min(7, int(days_per_week or 3)))
    train_days = _DAY_SPREAD[n]

    you_said = f' You said: "{identity_statement}"' if identity_statement else ""
    out: list[Reminder] = []
    for d in train_days:
        out.append(Reminder(
            id=f"eve-{d}", weekday=_PREV_DAY[d], hour=20, minute=0,
            title="Tomorrow you train",
            body="Lay your gear out tonight. Tomorrow is a vote for who you're becoming.",
        ))
        out.append(Reminder(
            id=f"pre-{d}", weekday=d, hour=hour, minute=0,
            title="Training day",
            body=f"Time to show up.{you_said}".strip(),
        ))
        post_h, post_m = hour + (post_offset_min // 60), post_offset_min % 60
        if post_h < 24:
            out.append(Reminder(
                id=f"log-{d}", weekday=d, hour=post_h, minute=post_m,
                title="Log your session",
                body="Done training? Tap to log it and lock in the win.",
            ))
    return out


def plan_as_dicts(reminders: list[Reminder]) -> list[dict]:
    return [asdict(r) for r in reminders]
