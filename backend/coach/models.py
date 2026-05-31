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
    # Implementation intention scaffold (Atomic Habits ch.5): "When X, I will Y at Z"
    cue: str | None = None                      # "after morning coffee"
    location: str | None = None                 # "at the gym" / "in the garage"
    # Minimum-viable variant of this action — the 2-minute-rule fallback
    # (Atomic Habits ch.13). Used when receptivity is low so the user does
    # SOMETHING rather than nothing.
    minimum_dose: str | None = None             # "just put on shoes + 5 squats"
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
    # Atomic Habits ch.2: "Every action you take is a vote for the type of
    # person you wish to become." We tally those votes from VerifiedEvents.
    # The count is derived (not user-settable) — kept here for fast reads.
    votes_cast: int = 0
    # The anchor habit captured at intake — used to author implementation
    # intentions ("right after MORNING_ANCHOR, I will…"). Ch.5 habit stacking.
    anchor_habit: str | None = None
    created_at: datetime = Field(default_factory=_now)


# ---------------------------------------------------------------------------
# The coach's persistent model of the user (Section 4.3).
# ---------------------------------------------------------------------------

class UserProfile(BaseModel):
    """Built during INTAKE and continuously updated."""
    user_id: str
    domain: str
    answers: dict[str, str] = Field(default_factory=dict)
    # `derived` is whatever the LLM extracted from intake answers — different
    # providers shape this differently (OpenAI tends to return lists for
    # multi-valued fields like injuries; Anthropic stays scalar). We accept
    # both rather than fight the model. Persona code that READS this should
    # coerce defensively (str(value) or " ".join(value)).
    derived: dict[str, str | int | float | list[str]] = Field(default_factory=dict)
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
    # --- Calibration phase (Section: onboarding, "real coach" rework) -------
    # Every new program starts in CALIBRATION — the first week is a structured
    # assessment of the user's actual capacity. After N calibration sessions,
    # the persona transitions to ACTIVE phase and builds the real program
    # using observed data (not self-reported / generic defaults).
    #
    # Default is "active" so existing personas and pre-rework users keep
    # working without migration — only personas that have been migrated to
    # the new flow create programs with phase="calibration".
    phase: Literal["calibration", "active"] = "active"
    # Index into the persona's calibration session list (0..N-1).
    # When this hits the persona's calibration length, phase flips to active.
    calibration_index: int = 0
    # Observed top sets keyed by lift slot (e.g. "bench", "squat", "row").
    # Each entry is the user's logged top clean set during calibration,
    # plus a derived estimated 1RM and a percentile/label from the
    # benchmark engine. Schema:
    #   {"bench": {"reps": 5, "load_lb": 145, "est_1rm_lb": 165,
    #              "percentile": 0.45, "label": "novice"},
    #    "squat": {...},
    #    ...}
    # After calibration completes, the persona reads this to set starting
    # loads AND to pick a program emphasis (the weakest lift).
    calibration_results: dict[str, dict[str, float | int | str]] = Field(default_factory=dict)
    # The slot the persona picked as the emphasis for the active program.
    # Drives extra volume / frequency on the weakest movement. Set when
    # transitioning calibration → active.
    emphasis_slot: str | None = None
    # Pause state (v2 Coach tab Shape E + return-after-absence "give me a week").
    # When set and in the future, the coach is intentionally silent until then;
    # the Coach tab renders the pause shape and the scheduler should suppress
    # nudges. None = active. Cleared on resume.
    paused_until: datetime | None = None


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


class SetLog(BaseModel):
    """
    One completed set within an exercise.

    `reps` is what the user actually finished (may be less than prescribed if
    they ran out of gas). `load_lb` is what they used — None for bodyweight
    lifts (pullups, planks). Order in the parent `ExerciseLog.sets` list is
    the order performed.
    """
    reps: int
    load_lb: float | None = None


class ExerciseLog(BaseModel):
    """
    Per-exercise outcome captured by the user during a session log.

    Replaces session-level outcome tracking (Section 5: each exercise is its
    own atomic action). The session-level outcome on the Nudge is *derived*
    from the rollup across these logs — done iff every exercise is done,
    skipped iff every exercise is skipped, partial otherwise.

    `sets` is the per-set history (Strong / Hevy style) — each set's actual
    reps + load. `actual_reps` / `actual_load_lb` are the *top set* (the
    heaviest load completed, with reps as tiebreaker) — kept as a flat field
    so legacy persona code and the calibration top_sets derivation don't
    have to learn the list shape. Both nil-able because a skipped exercise
    has nothing to record and bodyweight lifts omit load entirely.

    `calibration_slot` is echoed back from the prescription so the lifecycle
    can derive the legacy `top_sets` dict (keyed by slot) without re-running
    the persona. Empty / None for active-phase logs.
    """
    outcome: NudgeOutcome
    sets: list[SetLog] = Field(default_factory=list)
    actual_reps: int | None = None
    actual_load_lb: float | None = None
    actual_sets: int | None = None
    note: str | None = None
    calibration_slot: str | None = None


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
    # Structured top-set data, captured during CALIBRATION phase. Keyed by
    # calibration slot (e.g. "squat", "bench"); value is {reps, load_lb}.
    # The persona's progression_rules reads this on calibration logs to
    # populate program.calibration_results. Derived from `exercise_logs`
    # entries whose prescription carried a `calibration_slot` — kept on the
    # Nudge as a flat field so persona code that already reads it doesn't
    # have to learn the new shape. Empty for normal active-phase logs.
    top_sets: dict[str, dict[str, float]] = Field(default_factory=dict)
    # Per-exercise outcomes for this session, keyed by the prescribed exercise
    # name. The session-level `outcome` above is the rollup; this is the
    # source of truth for what actually happened lift-by-lift (Section 5 —
    # each exercise is the atomic action). Empty for nudge replies and other
    # paths where the user didn't tap through a per-exercise UI.
    exercise_logs: dict[str, ExerciseLog] = Field(default_factory=dict)


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

    # Atomic Habits ch.2: votes cast toward the identity. Mirrored here so
    # the iOS client can show "127 votes for who you're becoming" without a
    # second round-trip. Grown only via grow() — same mirror rules apply.
    identity_votes: int = 0

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

        # 4) Identity vote — Atomic Habits ch.2. Every verified session is one
        # more vote for who the user is becoming. Surfaced on the summit.
        self.identity_votes += 1
        ripples.append(f"another vote for who you're becoming ({self.identity_votes} total)")

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
    name: str                  # "Back Squat"
    sets: int                  # 3
    reps: int                  # 5
    load_lb: float | None      # 135 — None for bodyweight
    rest_seconds: int = 120
    notes: str = ""
    # Optional — when set, this is a duration-based exercise (cardio, plank,
    # carry). iOS renders "25 min" instead of "Nx{reps}" when present.
    # sets/reps still meaningful for interval work (e.g. 6 sets × 1 min).
    duration_min: int | None = None
    # When set, this exercise is a calibration probe for the named slot
    # (e.g. "squat", "bench", "pullup"). The iOS log sheet shows a "top
    # clean set" form for this exercise (reps + load_lb), and the user's
    # input flows back to the backend as nudge.top_sets[<slot>].
    # Set only during the calibration phase; None for normal active-phase
    # prescriptions.
    calibration_slot: str | None = None


# ---------------------------------------------------------------------------
# Coach Journal — the agent's narrative memory of the user (Principle 2.2:
# Persistence). This is the layer that separates "a coach who knows you"
# from "yet another tracker." Every meaningful event appends one short
# observation written by the LLM in the coach's own voice. The full journal
# is fed back as context for every subsequent LLM call, so the system
# accumulates real understanding rather than re-deriving it from scratch.
# ---------------------------------------------------------------------------

class JournalEntry(BaseModel):
    """One LLM-authored observation written after a meaningful event."""
    id: str = Field(default_factory=_uid)
    at: datetime = Field(default_factory=_now)
    # What triggered this entry — intake, log, reply, adapt, tick, etc.
    # Keeps the journal queryable without parsing the text.
    kind: str
    # The observation itself, in the coach's voice. ONE sentence, terse.
    text: str
    # Whether the coach thinks the user should hear this directly. False by
    # default — most journal entries are private notes. surface=True drives
    # the "From your coach" card in the iOS Today tab (Section 6).
    surface: bool = False
    # If surface=True, the LLM's reason. Helps debug surfacing logic.
    reason_for_surface: str | None = None


class CoachJournal(BaseModel):
    """The coach's running notebook about ONE user. Append-only in practice."""
    user_id: str
    entries: list[JournalEntry] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=_now)

    def append(self, entry: JournalEntry) -> None:
        self.entries.append(entry)
        self.updated_at = entry.at

    def recent(self, n: int = 10) -> list[JournalEntry]:
        return self.entries[-n:]

    def latest_surfaced(self) -> JournalEntry | None:
        """Most recent surface=True entry that hasn't yet been acknowledged.

        v1 doesn't track acknowledgment — every call returns the latest. The
        iOS layer can dedupe on entry.id. Good enough until we see a real
        case where the same observation keeps reappearing.
        """
        for e in reversed(self.entries):
            if e.surface:
                return e
        return None


# ---------------------------------------------------------------------------
# Coach memory of program adjustments (the "real coach who remembers what you
# told them" feature). When a user pushes back on the program — "this hurts",
# "too much volume", "I hate burpees" — we don't just one-off swap it. We
# record a STANDING CONSTRAINT that gets fed into every future program build,
# enforced at validation, and applied at session render. The decision sticks.
# ---------------------------------------------------------------------------


class ProgramAdjustment(BaseModel):
    """One decision the user made about their program, remembered forever.

    Two scopes:
      - "exercise": a per-movement swap/avoid ("barbell squat hurts my knee").
        target_exercise is the thing they reacted to; replacement_exercise is
        what we put in its place (if any).
      - "program": a whole-program change ("cut the volume, I'm wiped"). No
        single target — the directive drives a regeneration.

    `constraint` is the LLM-distilled, build-prompt-ready instruction (e.g.
    "Avoid Barbell Squat and other deep-knee-flexion barbell work — user
    reports left knee pain; prefer machine/goblet variants"). This is the
    text we inject into future split-planner and exercise-picker prompts.

    `active` lets a user later retract a constraint without us deleting the
    history (a real coach remembers "we tried that and undid it").
    """
    id: str = Field(default_factory=_uid)
    at: datetime = Field(default_factory=_now)
    user_id: str
    scope: Literal["exercise", "program"]
    # The raw free-form text the user wrote. Preserved verbatim — it's the
    # primary signal and we never want to lose the user's own words.
    user_note: str
    target_exercise: str | None = None
    replacement_exercise: str | None = None
    # The build-prompt-ready distilled instruction. Always set.
    constraint: str
    # Coach-voice reply shown back to the user when the adjustment lands.
    coach_response: str
    active: bool = True


class AdjustmentLog(BaseModel):
    """All program adjustments for ONE user. Append-mostly."""
    user_id: str
    adjustments: list[ProgramAdjustment] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=_now)

    def append(self, adj: ProgramAdjustment) -> None:
        self.adjustments.append(adj)
        self.updated_at = adj.at

    def active_constraints(self) -> list[ProgramAdjustment]:
        """The constraints a fresh build must honor — active ones only."""
        return [a for a in self.adjustments if a.active]

    def avoided_exercises(self) -> set[str]:
        """Lower-cased exercise names the user has asked us to stop prescribing.

        An exercise-scope adjustment with a target but no replacement is a
        pure avoid. One WITH a replacement is also an avoid of the target —
        the replacement took its place, so the original shouldn't resurface.
        """
        out: set[str] = set()
        for a in self.adjustments:
            if a.active and a.scope == "exercise" and a.target_exercise:
                out.add(a.target_exercise.lower())
        return out


class Session(BaseModel):
    """A single prescribed workout (the content of one AtomicAction)."""
    id: str = Field(default_factory=_uid)
    name: str                                  # "Workout A"
    summary: str = ""                          # "Full body — quads, chest, mid-back"
    exercises: list[ExercisePrescription]
    expected_minutes: int = 45
    progression_rule: str = ""                 # text the coach can show on adaptation


# ---------------------------------------------------------------------------
# iPhone signals (Section 8.1) — the on-device sensors that let the coach act
# without being asked. Three magical surfaces:
#
#   1) ReadinessSnapshot — HealthKit sleep + resting HR + HRV → a morning
#      readiness score. The coach reads it BEFORE prescribing and dials the
#      ask up or down. "You slept 5h and your resting HR is up — easing off."
#   2) TrainingPlace — a geofence the brain LEARNS from where sessions get
#      logged. Arriving fires "you're at the gym, session's ready"; leaving
#      without logging nudges a log prompt. The phone knows where you train.
#   3) DetectedWorkout — a HealthKit workout that overlaps the prescribed
#      window. One tap auto-logs the session as done, enriched with the real
#      duration / calories / heart rate. The loop closes without typing.
#
# These are the SECOND verification source (Section 9.1, source="sensor"):
# they don't just inform timing, they can grow the world honestly.
# ---------------------------------------------------------------------------

class ReadinessSnapshot(BaseModel):
    """One morning's recovery picture, read off HealthKit by the iOS client.

    Raw signals are sent up; the SCORE and BAND are derived server-side
    (coach.recovery.score_readiness) so the scoring rule is deterministic and
    testable in Python rather than scattered in Swift. The client may also
    send the user's own trailing baselines (their normal resting HR / HRV) so
    we score today against the user, not a population norm.
    """
    user_id: str
    at: datetime = Field(default_factory=_now)
    sleep_hours: float | None = None
    resting_hr: float | None = None          # bpm, last night
    hrv_ms: float | None = None              # HRV SDNN, ms
    # The user's own trailing normals, computed on-device (14-day medians).
    resting_hr_baseline: float | None = None
    hrv_baseline: float | None = None
    # Derived server-side. 0..100; band ∈ {rest, easy, ready, primed, unknown}.
    score: int = 0
    band: str = "unknown"
    # Multi-day signal (Smarter recovery): accumulated sleep deficit over the
    # last week, in hours, derived from the vitals time series. Lowers the
    # score so a string of short nights drags readiness down even after one
    # decent night. None when there's no sleep history to compute it from.
    sleep_debt_h: float | None = None

    @property
    def day(self) -> str:
        return self.at.date().isoformat()


class TrainingPlace(BaseModel):
    """The geofence the brain learned for where this user trains.

    Built by accumulating coordinate observations posted when the user starts
    or logs a session (coach.recovery.update_place_centroid). Once `confidence`
    crosses a threshold the iOS client starts region-monitoring it; arrivals
    and departures then drive contextual nudges.
    """
    user_id: str
    lat: float
    lon: float
    radius_m: float = 150.0
    label: str = "your gym"
    samples: int = 0
    confidence: float = 0.0                  # 0..1, grows with consistent samples
    updated_at: datetime = Field(default_factory=_now)

    @property
    def monitorable(self) -> bool:
        """Enough corroboration to be worth a geofence (Rubric D3 — restraint:
        we don't fence a one-off location)."""
        return self.samples >= 2 and self.confidence >= 0.5


class VitalSample(BaseModel):
    """One reading of one HealthKit metric at one moment.

    The unit of the broad-ingestion time series (coach.vitals). The iOS client
    reads everything Health will grant — body mass, sleep stages, VO2max,
    steps, resting HR, … — and posts batches of these; the backend stores them
    as a rolling per-metric history so the coach can reason about TRENDS, not
    just the latest point. `metric` is a canonical key from coach.vitals.METRICS;
    the user binding lives at the store layer (like AIProgram), not on the row.
    """
    metric: str
    value: float
    unit: str = ""
    at: datetime = Field(default_factory=_now)
