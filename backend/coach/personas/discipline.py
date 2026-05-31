"""
Discipline persona — the "75-Hard-style" goal template.

Strict, no-skip, six days a week, two-a-days collapsed into one Session
(an AM lift block + a PM cardio/mobility block on the same prescription).
The defining mechanic is the **streak + contract**: every "done" advances
days_completed; any "skipped" (or "ignored") resets it to zero by default.
The user picked this template because they want it strict — softening is
the failure mode here, not strictness.

Two non-negotiables:
  - SAFETY OVERRIDES THE CONTRACT. Pain in the friction note triggers a
    pause (no streak reset) + a doctor handoff. The 75 Hard tradition does
    not include "push through pain" — it includes mental discipline, not
    medical recklessness.
  - We never SUGGEST skipping. Sleep-deprived users get a *lighter* PM
    workout, not a skipped one. Two workouts is the contract.

MVP scope (this file):
  - Cycle defaults to "75_classic" (hard reset on miss). User-facing cycle
    picker (75 soft / 30 starter / open-ended) is documented in the design
    doc but deferred to a v2.1 onboarding revision.
  - Photo block, water/reading checklist, and HealthKit-driven adaptation
    are iOS-side composable blocks — see design/v2/composable-blocks.md.
    The persona surfaces these via the session.notes string, not as
    structured fields.
  - "Two-a-days" render as one Session with both blocks side by side. The
    iOS row formatting handles duration_min for the PM cardio block.

Per design/v2/templates/05-discipline.md.
"""

from __future__ import annotations

from .base import IntakeQuestion, Persona
from ..calibration import (
    lifting_calibration_days,
    record_top_sets,
    starting_load_from_calibration,
    weakest_lift,
)
from ..exercises import catalog, Exercise
from ..models import (
    ExercisePrescription,
    Habit,
    Milestone,
    ProgramState,
    Session,
    UserProfile,
)


_LOADED_EQUIPMENT = {"barbell", "dumbbell", "cable", "kettlebells", "machine",
                     "e-z curl bar"}


# Slot ladders — preferred first, fallback last. Same picker as other personas.
_SLOT_LADDERS: dict[str, list[str]] = {
    "bench":     ["Barbell Bench Press - Medium Grip", "Dumbbell Bench Press", "Pushups"],
    "squat":     ["Barbell Squat", "Goblet Squat", "Dumbbell Squat", "Bodyweight Squat"],
    "deadlift":  ["Barbell Deadlift", "Stiff-Legged Dumbbell Deadlift", "Single Leg Glute Bridge"],
    "ohp":       ["Standing Military Press", "Standing Dumbbell Press", "Pushups"],
    "row":       ["Bent Over Barbell Row", "One-Arm Dumbbell Row", "Inverted Row"],
    "pullup":    ["Pullups", "Band Assisted Pull-Up", "Inverted Row"],
    "lunge":     ["Dumbbell Lunges", "Barbell Walking Lunge", "Bodyweight Walking Lunge"],
    "curl":      ["Barbell Curl", "Dumbbell Bicep Curl", "Chin-Up"],
    "tricep":    ["Triceps Pushdown", "Bench Dips", "Pushups"],
    # PM cardio / conditioning ladders — duration-driven.
    "run":       ["Trail Running/Walking", "Running, Treadmill", "Walking, Treadmill", "Trail Running/Walking"],
    "intervals": ["Trail Running/Walking", "Running, Treadmill", "Rope Jumping", "Trail Running/Walking"],
    "easy_aerobic": ["Bicycling", "Walking, Treadmill", "Trail Running/Walking"],
    # Mobility (rest-day Wed PM block).
    "mobility":  ["Hip Circles (prone)", "Cat Stretch", "Child's Pose"],
}


# Discipline uses the same lifting calibration battery — week 1 is assessment,
# the 75-day cycle counter only starts at day 0 of 75 AFTER calibration is done.
# The contract is the contract, but the contract begins on day-1-of-the-program,
# not day-1-of-life. A cycle that starts with a 30 lb bench because the user
# never told us their numbers isn't the contract — it's noise.
_CALIBRATION_LENGTH = 5
_CALIBRATION_DAYS = lifting_calibration_days(
    _SLOT_LADDERS,
    catalog().equipment_for_profile,
)


# Conservative defaults — discipline users vary wildly (someone doing their
# fourth 75 Hard vs a first-timer), so we start moderate and let progression
# do the work. Hypertrophy-style numbers; the lift portion borrows that
# template's progression because the cadence is similar.
_DISCIPLINE_DEFAULTS = {
    "bench_lb":     95,
    "squat_lb":     115,
    "deadlift_lb": 135,
    "ohp_lb":       65,
    "row_lb":       95,
    "lunge_lb":     30,    # dumbbell per hand
    "curl_lb":      45,
    "tricep_lb":    50,
    # 6-day rotation cursor — Mon..Sat, Sun is implicit rest.
    "day_index":    0,
    # Streak — this template's primary metric. Resets to 0 on miss.
    "days_completed":       0,
    "longest_streak":       0,
    "cycle_target":         75,    # default to 75-day classic
    # Standard hypertrophy-ish progression scaffolding.
    "consecutive_failed_sessions": 0,
    # PM cardio durations creep weekly — we hold the floor for now.
    "easy_minutes":  45,
    "long_minutes":  60,
    "interval_rounds": 6,
}


# --- Intake -------------------------------------------------------------------

def _intake(prof: UserProfile | None):
    return [
        IntakeQuestion(
            "goal",
            "What do you want to do — build muscle, get stronger, lose weight, "
            "stay fit and age well, or 75-Hard-style discipline?",
        ),
        # Benchmark inputs for calibration week (the cycle starts AFTER).
        IntakeQuestion(
            "sex",
            "Biological sex — male or female? (Used for strength benchmarks.)",
        ),
        IntakeQuestion(
            "age",
            "How old are you?",
            coerce=lambda s: int("".join(c for c in s if c.isdigit()) or "30"),
        ),
        IntakeQuestion(
            "bodyweight_lb",
            "What do you weigh, in lbs?",
            coerce=lambda s: int("".join(c for c in s if c.isdigit()) or "180"),
        ),
        IntakeQuestion(
            "experience",
            "Have you done a strict daily program before? (yes / "
            "I've tried / never)",
        ),
        IntakeQuestion(
            "prior_disordered",
            "Honest one: have you ever felt unable to stop training "
            "when sick or hurt? (yes / no / not sure)",
        ),
        IntakeQuestion(
            "days_per_week",
            "How many days per week — 6 is the contract; 7 if you want absolute daily.",
            coerce=lambda s: int("".join(c for c in s if c.isdigit()) or "6"),
        ),
        IntakeQuestion(
            "outdoor_access",
            "Can you get outside daily? (yes / sometimes / no — it's still doable indoors)",
        ),
        IntakeQuestion(
            "equipment",
            "What equipment do you have? (full gym / barbell+rack / dumbbells / bodyweight)",
        ),
        IntakeQuestion(
            "anchor_habit",
            "Pick one thing you do every morning without thinking. AM workout stacks right after.",
        ),
        IntakeQuestion(
            "training_location",
            "Where will the AM session happen?",
        ),
    ]


# --- Programming --------------------------------------------------------------

def _build_program(profile: UserProfile):
    """
    Start in CALIBRATION. The 75-day contract counter doesn't start until
    calibration is complete — entering a contract with unknown loads would
    set the user up to either sandbag or grind, both of which break the
    spirit of the contract.

    6-day rotation begins after calibration: 3 lifts + 3 cardio days,
    two-a-days collapsed per day.
    """
    program = ProgramState(
        user_id=profile.user_id,
        program_name="Discipline — Calibration → 75-day classic, 6 days/week",
        phase="calibration",
        calibration_index=0,
        progression={
            "day_index":              0,
            "days_completed":         0,
            "longest_streak":         0,
            "cycle_target":           75,
            "consecutive_failed_sessions": 0,
        },
        notes=["Week 1 is calibration — five short sessions. The 75-day "
               "contract starts after. Miss = reset to day 1. Safety "
               "overrides the contract — pain stops, not pushes."],
    )

    identity_id = "pending"
    milestones = [
        Milestone(
            title="Day 7", description="First week. The hardest one is over.",
            parent_identity_id=identity_id,
        ),
        Milestone(
            title="Day 30", description="First month. Most people quit before here.",
            parent_identity_id=identity_id,
        ),
        Milestone(
            title="Day 50", description="Past the dropout cliff.",
            parent_identity_id=identity_id,
        ),
        Milestone(
            title="Day 75", description="Cycle complete. You did what you said you'd do.",
            parent_identity_id=identity_id,
        ),
        Milestone(
            title="30 days after a reset",
            description="Proves resilience after failure — arguably harder than 75 straight.",
            parent_identity_id=identity_id,
        ),
    ]
    habits = [
        Habit(
            title="Two workouts per day",
            cadence="6x per week",
            parent_milestone_id=milestones[0].id,
        ),
        Habit(
            title="Daily photo + water + reading",
            cadence="daily",
            parent_milestone_id=milestones[0].id,
        ),
    ]
    return program, milestones, habits


# --- Sessions -----------------------------------------------------------------

def _prescribe(slot: str, prog_key: str | None, sets: int, reps: int, rest: int,
               program: ProgramState, equipment: set[str | None]) -> ExercisePrescription:
    ex: Exercise = catalog().pick_for_slot(_SLOT_LADDERS[slot], equipment)
    load = (program.progression.get(prog_key) if prog_key and ex.equipment in _LOADED_EQUIPMENT
            else None)
    return ExercisePrescription(
        name=ex.name,
        sets=sets,
        reps=reps,
        load_lb=load,
        rest_seconds=rest,
        notes=(ex.first_instruction() or "")[:140],
    )


def _prescribe_pm_run(program: ProgramState, equipment: set[str | None],
                       minutes: int, outdoors: bool, note: str) -> ExercisePrescription:
    """Single steady-state PM cardio block."""
    ladder = _SLOT_LADDERS["run"] if outdoors else _SLOT_LADDERS["easy_aerobic"]
    ex: Exercise = catalog().pick_for_slot(ladder, equipment)
    return ExercisePrescription(
        name=f"PM — {ex.name}",
        sets=1,
        reps=1,
        load_lb=None,
        rest_seconds=0,
        notes=note,
        duration_min=minutes,
    )


def _prescribe_pm_intervals(program: ProgramState, equipment: set[str | None]) -> ExercisePrescription:
    ex: Exercise = catalog().pick_for_slot(_SLOT_LADDERS["intervals"], equipment)
    rounds = int(program.progression.get("interval_rounds", 6))
    return ExercisePrescription(
        name=f"PM — {ex.name} intervals",
        sets=rounds,
        reps=1,
        load_lb=None,
        rest_seconds=90,
        notes=f"{rounds} rounds — 1 min hard / 1 min easy. RPE 8/10 on the hard.",
        duration_min=1,
    )


def _prescribe_mobility(program: ProgramState, equipment: set[str | None]) -> ExercisePrescription:
    ex: Exercise = catalog().pick_for_slot(_SLOT_LADDERS["mobility"], equipment)
    return ExercisePrescription(
        name=f"PM — {ex.name}",
        sets=1,
        reps=1,
        load_lb=None,
        rest_seconds=0,
        notes="45 min mobility flow. Outdoors if you can — counts as the outdoor block.",
        duration_min=45,
    )


def _outdoor_pref(profile: UserProfile) -> bool:
    raw = (profile.answers.get("outdoor_access") or "").lower()
    return "no" not in raw  # default to outdoors unless they explicitly said no


def _mon(program: ProgramState, profile: UserProfile) -> Session:
    """Mon — Upper Lift A + outdoor run."""
    eq = catalog().equipment_for_profile(profile.answers.get("equipment"))
    return Session(
        name="Mon — Upper Lift + Run",
        summary="Bench, OHP, pullup, curl + 45 min outdoor run",
        exercises=[
            _prescribe("bench",  "bench_lb",  5, 5,   120, program, eq),
            _prescribe("ohp",    "ohp_lb",    3, 8,   90,  program, eq),
            _prescribe("pullup", None,         3, 8,   90,  program, eq),
            _prescribe("curl",   "curl_lb",   3, 10,  60,  program, eq),
            _prescribe_pm_run(program, eq,
                              int(program.progression.get("easy_minutes", 45)),
                              outdoors=_outdoor_pref(profile),
                              note="Easy 5k pace. Outdoors counts as the outdoor block. "
                                   "+ photo, water, reading after."),
        ],
        expected_minutes=90,
        progression_rule="AM lifts progress double-progression style. PM run "
                         "stays at 45 min — distance creeps when you log 'felt easy' twice.",
    )


def _tue(program: ProgramState, profile: UserProfile) -> Session:
    """Tue — Lower Lift A + intervals."""
    eq = catalog().equipment_for_profile(profile.answers.get("equipment"))
    return Session(
        name="Tue — Lower Lift + Intervals",
        summary="Squat, RDL, walking lunge + interval cardio",
        exercises=[
            _prescribe("squat",    "squat_lb",    5, 5,  120, program, eq),
            _prescribe("deadlift", "deadlift_lb", 3, 8,  120, program, eq),
            _prescribe("lunge",    "lunge_lb",    3, 10, 60,  program, eq),
            _prescribe_pm_intervals(program, eq),
        ],
        expected_minutes=90,
        progression_rule="Lifts move on clean sets. Intervals add a round every "
                         "2 weeks once form holds.",
    )


def _wed(program: ProgramState, profile: UserProfile) -> Session:
    """Wed — Easy cardio + mobility flow (the lightest day)."""
    eq = catalog().equipment_for_profile(profile.answers.get("equipment"))
    return Session(
        name="Wed — Easy Cardio + Mobility",
        summary="Zone 2 cardio + mobility — the recovery day",
        exercises=[
            _prescribe_pm_run(program, eq, 45,
                              outdoors=_outdoor_pref(profile),
                              note="Conversational pace. Bike, jog, or brisk walk. "
                                   "Outdoors satisfies the outdoor block."),
            _prescribe_mobility(program, eq),
        ],
        expected_minutes=90,
        progression_rule="No load progression today. The point is recovery + "
                         "still showing up.",
    )


def _thu(program: ProgramState, profile: UserProfile) -> Session:
    """Thu — Upper Lift B (rotation of Mon) + outdoor run."""
    eq = catalog().equipment_for_profile(profile.answers.get("equipment"))
    return Session(
        name="Thu — Upper Lift + Run",
        summary="Row, OHP, bench, tricep + 45 min outdoor run",
        exercises=[
            _prescribe("row",    "row_lb",    5, 5,   120, program, eq),
            _prescribe("ohp",    "ohp_lb",    3, 8,   90,  program, eq),
            _prescribe("bench",  "bench_lb",  3, 8,   90,  program, eq),
            _prescribe("tricep", "tricep_lb", 3, 12,  60,  program, eq),
            _prescribe_pm_run(program, eq,
                              int(program.progression.get("easy_minutes", 45)),
                              outdoors=_outdoor_pref(profile),
                              note="Same run as Monday. Different conditions every day "
                                   "is part of the discipline."),
        ],
        expected_minutes=90,
        progression_rule="Same as Monday — lifts double-progression, run holds at 45 min.",
    )


def _fri(program: ProgramState, profile: UserProfile) -> Session:
    """Fri — Lower Lift B + conditioning circuit."""
    eq = catalog().equipment_for_profile(profile.answers.get("equipment"))
    return Session(
        name="Fri — Lower Lift + Conditioning",
        summary="Squat, deadlift, lunge + interval conditioning",
        exercises=[
            _prescribe("squat",    "squat_lb",    5, 5,  120, program, eq),
            _prescribe("deadlift", "deadlift_lb", 3, 5,  120, program, eq),
            _prescribe("lunge",    "lunge_lb",    3, 12, 60,  program, eq),
            _prescribe_pm_intervals(program, eq),
        ],
        expected_minutes=90,
        progression_rule="Friday is the test of the week. If you make it here, "
                         "you make the whole week.",
    )


def _sat(program: ProgramState, profile: UserProfile) -> Session:
    """Sat — Long cardio (single block, no AM lift)."""
    eq = catalog().equipment_for_profile(profile.answers.get("equipment"))
    minutes = int(program.progression.get("long_minutes", 60))
    return Session(
        name="Sat — Long Cardio",
        summary=f"{minutes} min long run, hike, or ride",
        exercises=[
            _prescribe_pm_run(program, eq, minutes,
                              outdoors=_outdoor_pref(profile),
                              note=f"{minutes} min steady. The week's signature workout. "
                                   "Outdoors strongly preferred — it's part of the point."),
        ],
        expected_minutes=minutes + 10,
        progression_rule="Add 5 min every 2 weeks until 90 min. Then hold.",
    )


_DAYS = [_mon, _tue, _wed, _thu, _fri, _sat]  # 6 days; Sun = implicit rest


def _next_session(program: ProgramState, profile: UserProfile) -> Session:
    if program.phase == "calibration":
        idx = max(0, min(program.calibration_index, _CALIBRATION_LENGTH - 1))
        return _CALIBRATION_DAYS[idx](program, profile)
    day_index = int(program.progression.get("day_index", 0))
    builder = _DAYS[day_index % 6]
    return builder(program, profile)


def _transition_to_active(program: ProgramState, profile: UserProfile) -> str:
    """
    Calibration complete — set starting loads from observed data (65%, same
    as strength because the AM lift block is strength-leaning), pick the
    emphasis slot, flip phase. The 75-day counter now starts at 0.
    """
    results = program.calibration_results
    progression = dict(program.progression)

    def load_for(slot: str, default: float) -> float:
        if slot in results:
            return starting_load_from_calibration(results[slot], pct_of_1rm=0.65)
        return default

    progression["bench_lb"]    = load_for("bench",    _DISCIPLINE_DEFAULTS["bench_lb"])
    progression["squat_lb"]    = load_for("squat",    _DISCIPLINE_DEFAULTS["squat_lb"])
    progression["deadlift_lb"] = load_for("deadlift", _DISCIPLINE_DEFAULTS["deadlift_lb"])
    progression["ohp_lb"]      = load_for("ohp",      _DISCIPLINE_DEFAULTS["ohp_lb"])
    progression["row_lb"]      = load_for("row",      _DISCIPLINE_DEFAULTS["row_lb"])
    progression["lunge_lb"]    = _DISCIPLINE_DEFAULTS["lunge_lb"]
    progression["curl_lb"]     = _DISCIPLINE_DEFAULTS["curl_lb"]
    progression["tricep_lb"]   = _DISCIPLINE_DEFAULTS["tricep_lb"]
    progression["easy_minutes"]  = _DISCIPLINE_DEFAULTS["easy_minutes"]
    progression["long_minutes"]  = _DISCIPLINE_DEFAULTS["long_minutes"]
    progression["interval_rounds"] = _DISCIPLINE_DEFAULTS["interval_rounds"]

    program.progression = progression
    program.phase = "active"
    program.emphasis_slot = weakest_lift(results)

    emphasis_phrase = (f" The contract gives extra attention to your weakest "
                       f"slot — {program.emphasis_slot}."
                       if program.emphasis_slot else "")
    program.notes.append(
        f"Calibration complete. Day 1 of 75 starts now.{emphasis_phrase}"
    )
    return ("Calibration done. Day 1 of 75 starts tomorrow. The contract is "
            "live." + emphasis_phrase)


# --- Adaptation ---------------------------------------------------------------

_PAIN_KEYWORDS = ("pain", "hurts", "hurt", "sharp", "shooting", "stabbing",
                  "tweaked", "tweak", "pulled", "strain", "strained")


def _looks_like_pain(friction: str | None) -> bool:
    if not friction:
        return False
    s = friction.lower()
    return any(k in s for k in _PAIN_KEYWORDS)


def _looks_like_exhaustion(friction: str | None) -> bool:
    """Sleep-deprivation signal — adapt intensity, never count."""
    if not friction:
        return False
    s = friction.lower()
    return any(k in s for k in ("couldn't sleep", "no sleep", "exhausted",
                                 "sleep deprived", "didn't sleep", "tired"))


def _progression_rules(program: ProgramState, recent_reports: list[dict]) -> tuple[ProgramState, str]:
    if not recent_reports:
        if program.phase == "calibration":
            return program, ("Week 1 — calibration. Five short sessions, then "
                             "the 75-day contract starts.")
        return program, "Day 1 of 75. The first one is the loudest."

    p = program.model_copy(deep=True)
    latest = recent_reports[0]
    outcome = latest.get("outcome")
    friction = latest.get("friction") or ""

    # =======================================================================
    # CALIBRATION PHASE — assessment only, no streak movement yet
    # =======================================================================
    if p.phase == "calibration":
        profile_obj: UserProfile | None = latest.get("profile")
        top_sets = latest.get("top_sets") or {}

        recorded: list[str] = []
        if profile_obj is not None and top_sets:
            recorded = record_top_sets(p, profile_obj, top_sets)

        # Pain DURING calibration just pauses — doesn't impact a contract
        # that hasn't started yet.
        if _looks_like_pain(friction):
            return p, ("Pain note during calibration. The contract hasn't "
                       "started — no streak to protect. See someone about "
                       "it before we keep assessing.")

        if outcome in ("done", "partial"):
            p.calibration_index = min(p.calibration_index + 1, _CALIBRATION_LENGTH)

        if p.calibration_index >= _CALIBRATION_LENGTH and profile_obj is not None:
            return p, _transition_to_active(p, profile_obj)

        summary = ", ".join(recorded) if recorded else "logged"
        progress = f"{p.calibration_index}/{_CALIBRATION_LENGTH} calibration sessions done"
        return p, f"{summary}. {progress}."

    # =======================================================================
    # ACTIVE PHASE — 75-day contract logic (unchanged from v1)
    # =======================================================================

    # Always advance the rotation cursor.
    p.progression["day_index"] = (int(p.progression.get("day_index", 0)) + 1) % 6

    # SAFETY OVERRIDES THE CONTRACT. Pain pauses the streak (does NOT reset)
    # and surfaces a doctor handoff. The contract doesn't care; safety does.
    if _looks_like_pain(friction):
        p.progression["consecutive_failed_sessions"] = 0
        return p, ("Pain note logged — pausing the streak, not resetting. "
                   "Sharp pain or anything that doesn't pass in a few days "
                   "is a doctor conversation. The contract waits.")

    if outcome == "done":
        p.progression["consecutive_failed_sessions"] = 0
        p.progression["days_completed"] = int(p.progression.get("days_completed", 0)) + 1
        p.progression["longest_streak"] = max(
            int(p.progression.get("longest_streak", 0)),
            int(p.progression["days_completed"]),
        )

        if _looks_like_exhaustion(friction):
            rationale = ("Day logged. Tired-day note seen — tomorrow's PM is "
                         "easy aerobic, not intervals. Still two workouts. "
                         "We adapt intensity, not count.")
        else:
            # Standard lift progression: bump on a "felt easy" or just on
            # consecutive cleans. Less generous than hypertrophy because
            # discipline users overshoot.
            felt_easy = "easy" in friction.lower() if friction else False
            if felt_easy:
                p.progression["bench_lb"]    = float(p.progression.get("bench_lb",  95))  + 5
                p.progression["squat_lb"]    = float(p.progression.get("squat_lb",  115)) + 10
                p.progression["deadlift_lb"] = float(p.progression.get("deadlift_lb", 135)) + 10
                rationale = (f"Day {p.progression['days_completed']} done — felt easy, "
                             "so +5 upper / +10 lower next time.")
            else:
                rationale = f"Day {p.progression['days_completed']} done. On track."

    elif outcome == "partial":
        p.progression["consecutive_failed_sessions"] = (
            int(p.progression.get("consecutive_failed_sessions", 0)) + 1
        )
        rationale = ("Partial counts toward the day, not toward progression. "
                     "Hold loads. Tomorrow we go again.")
        p.progression["days_completed"] = int(p.progression.get("days_completed", 0)) + 1

    elif outcome in ("skipped", "busy", "not_now", "ignored"):
        # The contract. Default behavior is hard reset for 75_classic.
        cycle = (p.progression.get("cycle") or "75_classic")
        if cycle == "open_ended":
            rationale = ("Missed. Streak holds (open-ended cycle). "
                         "Tomorrow's day is just the next day.")
        else:
            broke_at = int(p.progression.get("days_completed", 0))
            p.progression["days_completed"] = 0
            rationale = (f"Missed. The contract resets — broke at day {broke_at}. "
                         "Day 1 tomorrow if you want it. Or we go to soft. Your call.")

    else:
        rationale = "Holding."

    # Two consecutive partials -> small load deload. Same safety net.
    if int(p.progression.get("consecutive_failed_sessions", 0)) >= 2:
        for k in list(p.progression.keys()):
            if k.endswith("_lb") and isinstance(p.progression[k], (int, float)):
                p.progression[k] = max(20.0, round(float(p.progression[k]) * 0.92))
        p.progression["consecutive_failed_sessions"] = 0
        rationale += " Two consecutive partials — 8% load reduction across lifts."

    p.notes.append(rationale)
    return p, rationale


# --- Persona instance ---------------------------------------------------------

DISCIPLINE_PERSONA = Persona(
    domain="discipline",
    voice=(
        "You speak like a coach for someone who asked for strict. Short "
        "sentences. Imperative when it counts. Zero softening — the user "
        "would resent it. You reference the contract often: 'that's a no', "
        "'day 1 again', 'up to you'. You never say 'it's okay, life "
        "happens' — they didn't pick this template for that. But you are "
        "not a drill instructor — you don't perform toughness. You are "
        "tough because they asked for tough. Pain or injury overrides "
        "everything — that's the one place you soften without apology."
    ),
    safety_disclaimer=(
        "I program training to the contract you set. Safety overrides the "
        "contract: sharp pain, lingering pain, anything that feels wrong "
        "stops the cycle without resetting it. Doctor first, then we "
        "resume. The discipline is not about pushing through injury."
    ),
    intake_questions=_intake,
    build_program=_build_program,
    next_session=_next_session,
    progression_rules=_progression_rules,
    world_theme="forge",
    calibration_length=_CALIBRATION_LENGTH,
)
