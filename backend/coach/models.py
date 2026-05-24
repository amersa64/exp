"""
Core data model.

Implements:
  - Section 5: the four-level hierarchy (Identity → Milestones → Habits → Atomic Actions)
  - Section 4.3: everything the brain must persist
  - Section 9.1: the verification principle is enforced by `WorldState.grow()` which
    will only accept a VerifiedEvent — there is no setter that grows the world from
    in-app tapping. The mirror principle is structural, not procedural.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, PrivateAttr


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uid() -> str:
    return uuid4().hex[:12]


# ---------------------------------------------------------------------------
# Tracking primitives (Section 5.1) — same node, different data type.
# ---------------------------------------------------------------------------

class TrackingKind(str, Enum):
    BINARY = "binary"        # did it happen — yes/no
    COUNT = "count"          # how many — reps, glasses, sets
    DURATION = "duration"    # how long — minutes
    SCALE = "scale"          # 1–5 — RPE, mood, energy


class TrackingSpec(BaseModel):
    kind: TrackingKind
    target: float | int | None = None  # e.g. 3 sets, 45 min; None for binary
    unit: str | None = None            # "reps", "min", "glasses"


# ---------------------------------------------------------------------------
# The four levels (Section 5).
# ---------------------------------------------------------------------------

class AtomicAction(BaseModel):
    """Level 4 — the 2-minute, do-it-now thing that gets nudged & verified."""
    id: str = Field(default_factory=_uid)
    title: str                                  # "Squat 3x5 @ 135lb"
    description: str                            # the actual prescription
    tracking: TrackingSpec
    parent_habit_id: str
    # Implementation intention scaffold — "When X, I will do Y" (Section 3.2)
    cue: str | None = None                      # "after morning coffee"
    # Bookkeeping
    prescribed_for: datetime | None = None      # when the coach scheduled it
    expected_minutes: int = 20


class Habit(BaseModel):
    """Level 3 — recurring systems between milestones."""
    id: str = Field(default_factory=_uid)
    title: str                                  # "Strength training 3x/week"
    cadence: str                                # human-readable cadence
    parent_milestone_id: str
    active: bool = True


class Milestone(BaseModel):
    """Level 2 — waypoints; completing one is an unlock."""
    id: str = Field(default_factory=_uid)
    title: str                                  # "Squat 1.5x bodyweight"
    description: str
    parent_identity_id: str
    achieved_at: datetime | None = None


class Identity(BaseModel):
    """Level 1 — who the user is becoming. Identity-based, not outcome-based."""
    id: str = Field(default_factory=_uid)
    user_id: str
    statement: str                              # "I am a strong, energetic person"
    domain: str                                 # "fitness"
    created_at: datetime = Field(default_factory=_now)


# ---------------------------------------------------------------------------
# The coach's persistent model of the user (Section 4.3).
# ---------------------------------------------------------------------------

class UserProfile(BaseModel):
    """Built during INTAKE and continuously updated."""
    user_id: str
    domain: str
    answers: dict[str, str] = Field(default_factory=dict)
    derived: dict[str, str | int | float] = Field(default_factory=dict)
    # e.g. {"experience": "novice", "days_per_week": 3, "injuries": "none",
    #       "equipment": "barbell+rack", "1rm_squat_lb": 135}
    updated_at: datetime = Field(default_factory=_now)


class ProgramState(BaseModel):
    """The active plan and its progression state."""
    user_id: str
    program_name: str                           # e.g. "Linear Progression — Lower"
    week: int = 1
    session_index: int = 0                      # how many sessions completed
    progression: dict[str, float | int] = Field(default_factory=dict)
    # e.g. {"squat_lb": 135, "bench_lb": 95, "deadlift_lb": 185,
    #       "consecutive_easy_sessions": 0, "consecutive_failed_sessions": 0}
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# The nudge / reply / verification cycle.
# ---------------------------------------------------------------------------

class NudgeOutcome(str, Enum):
    PENDING = "pending"
    DONE = "done"
    PARTIAL = "partial"
    SKIPPED = "skipped"
    NOT_NOW = "not_now"
    BUSY = "busy"
    IGNORED = "ignored"          # auto, after timeout


class Nudge(BaseModel):
    """A prompt the agent fires (Section 7). Carries the prescription."""
    id: str = Field(default_factory=_uid)
    user_id: str
    action_id: str
    fired_at: datetime = Field(default_factory=_now)
    fire_window_until: datetime                 # past this it's marked IGNORED
    headline: str                               # the AI-generated body
    body: str
    implementation_intention: str | None = None
    outcome: NudgeOutcome = NudgeOutcome.PENDING
    outcome_at: datetime | None = None
    friction_note: str | None = None            # what got in the way
    # Decision-engine telemetry — feeds adaptation of timing
    fired_because: str = ""                      # e.g. "calendar_gap@1730, low recent steps"


class VerifiedEvent(BaseModel):
    """
    The ONLY thing that may grow the world (Section 9.1).

    Two valid sources:
      - "report"  : a user one-tap report on a real prescribed action
                    (acceptable for v1; later we corroborate with sensors)
      - "sensor"  : a HealthKit/Calendar signal that the action actually happened
    """
    id: str = Field(default_factory=_uid)
    user_id: str
    action_id: str                              # the AtomicAction that was prescribed
    nudge_id: str | None                        # which nudge produced this — may be None
                                                # only for sensor-detected unprompted action
    source: Literal["report", "sensor"]
    sensor: str | None = None                    # "healthkit.workout", "calendar.attended"
    at: datetime = Field(default_factory=_now)
    payload: dict[str, str | int | float] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# The growing world (Section 6) — derived state, mirror integrity enforced.
# ---------------------------------------------------------------------------

class WorldState(BaseModel):
    """
    Read-only aspiration and reflection (Principle 2.6, Section 6.3).

    Growth is a pure function of VerifiedEvents. There is no public setter that
    grows the world from in-app interaction. `grow()` is the ONLY entry point
    and it requires a VerifiedEvent.
    """
    user_id: str
    theme: str = "northwood"                    # derived from identity domain
    currency: int = 0                            # earned per verified action
    streak_days: int = 0                         # don't-break-the-chain
    longest_streak: int = 0
    last_verified_day: str | None = None        # ISO date string
    unlocked: list[str] = Field(default_factory=list)   # buildings/creatures
    living_systems: dict[str, float] = Field(default_factory=dict)
    # 0.0 = wilting, 1.0 = thriving — keyed by habit_id

    # Private guard: an internal flag that grow() must set, and that any persistence
    # layer can use to assert this object came from a verified mutation path.
    _last_growth_source: Optional[str] = PrivateAttr(default=None)

    def grow(self, event: VerifiedEvent, action: AtomicAction) -> list[str]:
        """
        The only path that grows the world. Returns a list of human-readable
        ripple events (Section 5: "the upward ripple") to display to the user.

        NOTE: if you find yourself wanting to call this without a VerifiedEvent,
        re-read Section 2 Principle 6 and Section 9.1. The answer is no.
        """
        ripples: list[str] = []
        today = event.at.date().isoformat()

        # 1) Currency — bottom of the hierarchy.
        gained = 10 if event.source == "sensor" else 7
        self.currency += gained
        ripples.append(f"+{gained} effort")

        # 2) Streak — loss aversion (Section 3.5).
        if self.last_verified_day != today:
            if self.last_verified_day:
                last = datetime.fromisoformat(self.last_verified_day).date()
                today_d = datetime.fromisoformat(today).date()
                if (today_d - last) == timedelta(days=1):
                    self.streak_days += 1
                else:
                    self.streak_days = 1
            else:
                self.streak_days = 1
            self.last_verified_day = today
            self.longest_streak = max(self.longest_streak, self.streak_days)
            ripples.append(f"streak: {self.streak_days} day{'s' if self.streak_days != 1 else ''}")

        # 3) Living system (the parent habit) — keep it thriving.
        habit_id = action.parent_habit_id
        cur = self.living_systems.get(habit_id, 0.5)
        self.living_systems[habit_id] = min(1.0, cur + 0.15)
        ripples.append("a living system in the world is thriving")

        self._last_growth_source = event.id
        return ripples

    def wilt(self, habit_id: str, days_since: int) -> None:
        """A habit lapsed — that part of the world stalls (Section 6.1 loss aversion)."""
        if habit_id in self.living_systems:
            decay = min(0.5, 0.05 * days_since)
            self.living_systems[habit_id] = max(0.0, self.living_systems[habit_id] - decay)


# ---------------------------------------------------------------------------
# Programming primitives the persona uses to actually prescribe sessions.
# ---------------------------------------------------------------------------

class ExercisePrescription(BaseModel):
    name: str               # "Back Squat"
    sets: int               # 3
    reps: int               # 5
    load_lb: float | None   # 135 — None for bodyweight
    rest_seconds: int = 120
    notes: str = ""


class Session(BaseModel):
    """A single prescribed workout (the content of one AtomicAction)."""
    id: str = Field(default_factory=_uid)
    name: str                                  # "Lower A"
    exercises: list[ExercisePrescription]
    expected_minutes: int = 45
    progression_rule: str = ""                 # text the coach can show on adaptation
