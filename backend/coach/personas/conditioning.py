"""
Conditioning persona — the "lose weight, get fit" goal template.

Hybrid: 3 lift days + 2 conditioning days (5-day rotation), built around
strength endurance (moderate rep, short rest) plus cardio (steady-state +
intervals). The aim is body-composition change via training stimulus + caloric
expenditure. Diet is explicitly NOT in scope (see safety_disclaimer + design
doc design/v2/templates/03-conditioning.md).

MVP scope (this file):
  - 5-day rotation, no compress-to-3 yet
  - HealthKit weight integration deferred to a separate ticket
  - Photo block deferred (built with discipline template)
  - Volume-reduction-on-slip adaptation deferred — for now standard slip
    handling matches strength

Per design/v2/templates/03-conditioning.md.
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
                     "e-z curl bar", "medicine ball"}


# The shared lifting calibration battery uses canonical slot names
# (squat / bench / row / deadlift / ohp / pullup). Conditioning's own
# active-phase logic uses "press" instead of "bench" for the chest movement,
# so we alias both names in the ladder — the calibration battery probes
# "bench" but conditioning's _SLOT_LADDERS["press"] is the same list.
_PRESS_LADDER = ["Barbell Bench Press - Medium Grip", "Dumbbell Bench Press", "Pushups"]

_SLOT_LADDERS: dict[str, list[str]] = {
    "squat":      ["Barbell Squat", "Goblet Squat", "Dumbbell Squat", "Bodyweight Squat"],
    "press":      _PRESS_LADDER,
    "bench":      _PRESS_LADDER,  # alias for calibration battery
    "row":        ["Bent Over Barbell Row", "One-Arm Dumbbell Row", "Inverted Row"],
    "deadlift":   ["Barbell Deadlift", "Stiff-Legged Dumbbell Deadlift", "Single Leg Glute Bridge"],
    "ohp":        ["Standing Military Press", "Standing Dumbbell Press", "Pushups"],
    "pullup":     ["Pullups", "Band Assisted Pull-Up", "Inverted Row"],
    "lunge":      ["Dumbbell Lunges", "Bodyweight Walking Lunge", "Stationary Bike"],
    "plank":      ["Plank", "Mountain Climbers", "Plank"],
    # Cardio "lifts" — duration-based. The persona picks one based on
    # equipment / preference (defaults to walking — works for everyone).
    "steady":     ["Trail Running/Walking", "Bicycling", "Walking, Treadmill", "Trail Running/Walking"],
    "intervals":  ["Trail Running/Walking", "Bicycling, Stationary", "Running, Treadmill", "Trail Running/Walking"],
    "circuit":    ["Rope Jumping", "Stairmaster", "Rowing, Stationary", "Rope Jumping"],
}


_CALIBRATION_LENGTH = 5
_CALIBRATION_DAYS = lifting_calibration_days(
    _SLOT_LADDERS,
    catalog().equipment_for_profile,
)


_CONDITIONING_DEFAULTS = {
    "squat_lb":    95,
    "bench_lb":    65,
    "deadlift_lb": 135,
    "row_lb":      65,
    "ohp_lb":      45,
    "lunge_lb":    25,  # dumbbell per hand
}


# --- Intake -------------------------------------------------------------------

def _intake(prof: UserProfile | None):
    return [
        IntakeQuestion(
            "goal",
            "What do you want to do — build muscle, get stronger, lose weight, "
            "stay fit and age well, or 75-Hard-style discipline?",
        ),
        # Benchmark inputs for calibration.
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
            "What do you weigh, in lbs? (Used for benchmarking and to "
            "set sensible cardio loads.)",
            coerce=lambda s: int("".join(c for c in s if c.isdigit()) or "180"),
        ),
        IntakeQuestion(
            "experience",
            "How would you describe your training experience — none, "
            "novice (under 6 months consistent), intermediate (1+ year), or advanced?",
        ),
        IntakeQuestion(
            "days_per_week",
            "How many days per week can you train? 3-5 works for conditioning.",
            coerce=lambda s: int("".join(c for c in s if c.isdigit()) or "4"),
        ),
        IntakeQuestion(
            "injuries",
            "Any current pain, injuries, or movements you should avoid? "
            "Describe them, or write 'none'.",
        ),
        IntakeQuestion(
            "equipment",
            "What equipment do you have? (full gym / barbell+rack / dumbbells / bodyweight)",
        ),
        IntakeQuestion(
            "anchor_habit",
            "Pick one thing you do every day without thinking. We'll stack training right after it.",
        ),
        IntakeQuestion(
            "training_location",
            "Where will the training actually happen?",
        ),
    ]


# --- Programming --------------------------------------------------------------

def _build_program(profile: UserProfile):
    """
    Start in CALIBRATION. Week 1 is the shared 5-session assessment; the
    5-day Conditioning rotation (3 lifts + 2 cardio) starts week 2 with
    loads built from observed numbers, including the 12-min walk/run that
    sets the cardio baseline.
    """
    program = ProgramState(
        user_id=profile.user_id,
        program_name="Conditioning — Calibration → 3 lift + 2 cardio (5x/week)",
        phase="calibration",
        calibration_index=0,
        progression={
            "day_index": 0,
            "consecutive_failed_sessions": 0,
            "steady_minutes":   25,
            "interval_rounds":  6,
        },
        notes=["Week 1 is calibration — five short assessments. Conditioning "
               "rotation starts week 2 with loads + cardio dose calibrated to "
               "your actual numbers."],
    )

    identity_id = "pending"
    milestones = [
        Milestone(
            title="4 weeks consistent",
            description="18+ sessions logged in 4 calendar weeks. The foundation.",
            parent_identity_id=identity_id,
        ),
        Milestone(
            title="First 5k run continuous",
            description="Or 10 miles bike, or 1km swim. Endurance threshold.",
            parent_identity_id=identity_id,
        ),
        Milestone(
            title="Squat bodyweight x5",
            description="Strength milestone — proves lifts haven't been hollow.",
            parent_identity_id=identity_id,
        ),
        Milestone(
            title="8 weeks consistent",
            description="The long-haul marker. Behavior change is real here.",
            parent_identity_id=identity_id,
        ),
    ]
    habits = [
        Habit(
            title="Strength training",
            cadence="3x per week",
            parent_milestone_id=milestones[0].id,
        ),
        Habit(
            title="Conditioning",
            cadence="2x per week",
            parent_milestone_id=milestones[0].id,
        ),
    ]
    return program, milestones, habits


# --- Sessions -----------------------------------------------------------------

def _prescribe(slot: str, prog_key: str, sets: int, reps: int, rest: int,
               program: ProgramState, equipment: set[str | None]) -> ExercisePrescription:
    ex: Exercise = catalog().pick_for_slot(_SLOT_LADDERS[slot], equipment)
    load = program.progression.get(prog_key) if ex.equipment in _LOADED_EQUIPMENT else None
    cue = ex.first_instruction() or ""
    return ExercisePrescription(
        name=ex.name,
        sets=sets,
        reps=reps,
        load_lb=load,
        rest_seconds=rest,
        notes=cue[:140],
    )


def _prescribe_cardio_steady(program: ProgramState, equipment: set[str | None]) -> ExercisePrescription:
    """Single steady-state cardio block, duration in minutes."""
    ex: Exercise = catalog().pick_for_slot(_SLOT_LADDERS["steady"], equipment)
    mins = int(program.progression.get("steady_minutes", 25))
    return ExercisePrescription(
        name=ex.name,
        sets=1,
        reps=1,
        load_lb=None,
        rest_seconds=0,
        notes="Conversational pace. You can talk but not sing.",
        duration_min=mins,
    )


def _prescribe_cardio_intervals(program: ProgramState, equipment: set[str | None]) -> ExercisePrescription:
    """Interval block — N rounds of 1 minute hard, 1 minute easy."""
    ex: Exercise = catalog().pick_for_slot(_SLOT_LADDERS["intervals"], equipment)
    rounds = int(program.progression.get("interval_rounds", 6))
    return ExercisePrescription(
        name=ex.name,
        sets=rounds,
        reps=1,
        load_lb=None,
        rest_seconds=60,
        notes=f"{rounds} rounds — 1 min hard / 1 min easy. RPE 8/10 on the hard.",
        duration_min=1,
    )


def _lift_a(program: ProgramState, profile: UserProfile) -> Session:
    eq = catalog().equipment_for_profile(profile.answers.get("equipment"))
    return Session(
        name="Lift A",
        summary="Full body — squat, press, row, core",
        exercises=[
            _prescribe("squat", "squat_lb", 3, 8, 90, program, eq),
            _prescribe("press", "bench_lb", 3, 8, 90, program, eq),
            _prescribe("row",   "row_lb",   3, 10, 60, program, eq),
            _prescribe("plank", "row_lb",   3, 30, 30, program, eq),  # 30 = hold seconds, not load-based
        ],
        expected_minutes=35,
        progression_rule="Hit all sets clean → +2.5 lb upper / +5 lb lower next time.",
    )


def _cardio_steady(program: ProgramState, profile: UserProfile) -> Session:
    eq = catalog().equipment_for_profile(profile.answers.get("equipment"))
    return Session(
        name="Cardio — steady",
        summary="Steady-state aerobic — zone 2",
        exercises=[_prescribe_cardio_steady(program, eq)],
        expected_minutes=int(program.progression.get("steady_minutes", 25)) + 5,
        progression_rule="Stay at conversational pace. We add 1 minute every 2 weeks.",
    )


def _lift_b(program: ProgramState, profile: UserProfile) -> Session:
    eq = catalog().equipment_for_profile(profile.answers.get("equipment"))
    return Session(
        name="Lift B",
        summary="Full body — deadlift variation, press, pull",
        exercises=[
            _prescribe("deadlift", "deadlift_lb", 3, 8, 90, program, eq),
            _prescribe("ohp",      "ohp_lb",      3, 8, 90, program, eq),
            _prescribe("row",      "row_lb",      3, 10, 60, program, eq),
            _prescribe("lunge",    "lunge_lb",    3, 10, 60, program, eq),
        ],
        expected_minutes=35,
        progression_rule="Hit all sets clean → +2.5 lb upper / +5 lb lower next time.",
    )


def _cardio_intervals(program: ProgramState, profile: UserProfile) -> Session:
    eq = catalog().equipment_for_profile(profile.answers.get("equipment"))
    return Session(
        name="Cardio — intervals",
        summary="Interval training — RPE 8/10",
        exercises=[_prescribe_cardio_intervals(program, eq)],
        expected_minutes=20,
        progression_rule="Add 1 round every 2 weeks once form holds.",
    )


def _lift_c(program: ProgramState, profile: UserProfile) -> Session:
    """Strength endurance circuit — same lifts, lighter loads, shorter rest."""
    eq = catalog().equipment_for_profile(profile.answers.get("equipment"))
    return Session(
        name="Lift C — circuit",
        summary="Full body circuit — strength endurance",
        exercises=[
            _prescribe("squat", "squat_lb", 3, 12, 45, program, eq),
            _prescribe("press", "bench_lb", 3, 12, 45, program, eq),
            _prescribe("row",   "row_lb",   3, 12, 45, program, eq),
            _prescribe("lunge", "lunge_lb", 3, 10, 45, program, eq),
            _prescribe("plank", "row_lb",   3, 45, 30, program, eq),  # 45 = seconds
        ],
        expected_minutes=30,
        progression_rule="Circuit style — minimal rest. Load adds same as Lift A/B.",
    )


_DAYS = [_lift_a, _cardio_steady, _lift_b, _cardio_intervals, _lift_c]


def _next_session(program: ProgramState, profile: UserProfile) -> Session:
    if program.phase == "calibration":
        idx = max(0, min(program.calibration_index, _CALIBRATION_LENGTH - 1))
        return _CALIBRATION_DAYS[idx](program, profile)
    day_index = int(program.progression.get("day_index", 0))
    builder = _DAYS[day_index % 5]
    return builder(program, profile)


def _transition_to_active(program: ProgramState, profile: UserProfile) -> str:
    """
    Calibration complete — starting loads at 55% of observed 1RM (lower than
    strength/hypertrophy because conditioning reps are higher and rest is
    shorter, so a too-heavy starting load tanks adherence).
    """
    results = program.calibration_results
    progression = dict(program.progression)

    def load_for(slot: str, default: float) -> float:
        if slot in results:
            return starting_load_from_calibration(results[slot], pct_of_1rm=0.55)
        return default

    # Conditioning's progression dict uses "bench_lb" for the chest movement
    # but slot ladder calls it "press". The calibration battery probes "bench",
    # so we map straight across.
    progression["squat_lb"]    = load_for("squat",    _CONDITIONING_DEFAULTS["squat_lb"])
    progression["bench_lb"]    = load_for("bench",    _CONDITIONING_DEFAULTS["bench_lb"])
    progression["row_lb"]      = load_for("row",      _CONDITIONING_DEFAULTS["row_lb"])
    progression["deadlift_lb"] = load_for("deadlift", _CONDITIONING_DEFAULTS["deadlift_lb"])
    progression["ohp_lb"]      = load_for("ohp",      _CONDITIONING_DEFAULTS["ohp_lb"])
    progression["lunge_lb"]    = _CONDITIONING_DEFAULTS["lunge_lb"]

    program.progression = progression
    program.phase = "active"
    program.emphasis_slot = weakest_lift(results)

    emphasis_phrase = (f" Emphasis: {program.emphasis_slot} — extra attention "
                       f"on the lift day where it shows up."
                       if program.emphasis_slot else "")
    program.notes.append(
        f"Calibration complete. Starting loads from observed data."
        f"{emphasis_phrase}"
    )
    return ("Calibration done. The rotation starts now with your numbers."
            + emphasis_phrase)


# --- Adaptation ---------------------------------------------------------------

def _progression_rules(program: ProgramState, recent_reports: list[dict]) -> tuple[ProgramState, str]:
    if not recent_reports:
        if program.phase == "calibration":
            return program, ("Week 1 — calibration. Five sessions to set "
                             "loads + cardio dose, then the rotation begins.")
        return program, "First session — establishing baseline."

    p = program.model_copy(deep=True)
    latest = recent_reports[0]
    outcome = latest.get("outcome")
    session_name = latest.get("session_name", "")

    # =======================================================================
    # CALIBRATION PHASE
    # =======================================================================
    if p.phase == "calibration":
        profile_obj: UserProfile | None = latest.get("profile")
        top_sets = latest.get("top_sets") or {}

        recorded: list[str] = []
        if profile_obj is not None and top_sets:
            recorded = record_top_sets(p, profile_obj, top_sets)

        if outcome in ("done", "partial"):
            p.calibration_index = min(p.calibration_index + 1, _CALIBRATION_LENGTH)

        if p.calibration_index >= _CALIBRATION_LENGTH and profile_obj is not None:
            return p, _transition_to_active(p, profile_obj)

        summary = ", ".join(recorded) if recorded else "logged"
        progress = f"{p.calibration_index}/{_CALIBRATION_LENGTH} calibration sessions done"
        return p, f"{summary}. {progress}."

    # =======================================================================
    # ACTIVE PHASE — 5-day rotation (unchanged)
    # =======================================================================

    # Advance to next day in the rotation.
    p.progression["day_index"] = (int(p.progression.get("day_index", 0)) + 1) % 5

    is_cardio = "Cardio" in session_name
    is_lift_a = "Lift A" in session_name or "Lift A" == session_name
    is_lift_b = "Lift B" in session_name

    if outcome == "done":
        p.progression["consecutive_failed_sessions"] = 0
        if is_cardio:
            # Cardio progresses on a slower schedule — 1 min steady / 1 round
            # intervals every 2 weeks. For MVP, we don't track week boundaries;
            # we add every 4th cardio session (= 2 weeks at 2 cardio days/week).
            # Simpler: just hold cardio for now, rely on weekly letter to
            # surface progression manually. v2.x adds week-boundary tracking.
            rationale = "Cardio done — holding pace. Two weeks of clean and we add."
        else:
            if is_lift_a or is_lift_b:
                p.progression["squat_lb"] = float(p.progression.get("squat_lb", 95)) + 5
                p.progression["bench_lb"] = float(p.progression.get("bench_lb", 65)) + 2.5
                p.progression["row_lb"]   = float(p.progression.get("row_lb", 65)) + 2.5
                rationale = "Session clean — +5 squat / +2.5 upper next time."
            else:  # circuit
                # Circuit holds load (12 reps already at the edge). Progression
                # is to add a round once a month, not to add load.
                rationale = "Circuit done — holding load. Reps at 12 is the working set."

    elif outcome == "partial":
        p.progression["consecutive_failed_sessions"] = (
            int(p.progression.get("consecutive_failed_sessions", 0)) + 1
        )
        rationale = "Partial — holding load. Repeat next time."

    elif outcome in ("skipped", "busy", "not_now", "ignored"):
        rationale = f"{outcome} — no change. We adjust next week if it becomes a pattern."

    else:
        rationale = "Holding."

    # Two consecutive partials → light deload
    if int(p.progression.get("consecutive_failed_sessions", 0)) >= 2:
        for k in list(p.progression.keys()):
            if k.endswith("_lb") and isinstance(p.progression[k], (int, float)):
                p.progression[k] = max(20.0, float(p.progression[k]) * 0.90)
        p.progression["consecutive_failed_sessions"] = 0
        rationale += " Two consecutive misses — 10% deload across lifts."

    p.notes.append(rationale)
    return p, rationale


# --- Persona instance ---------------------------------------------------------

CONDITIONING_PERSONA = Persona(
    domain="conditioning",
    voice=(
        "You speak like a coach for someone trying to drop fat and feel better. "
        "Specific, never preachy. You acknowledge that visible change is slow "
        "and weight is volatile. You never moralize about food. You never use "
        "the words 'shred', 'transform', or 'cleanse'. If the user is tired "
        "or stressed, you shrink the conditioning ask before you increase it."
    ),
    safety_disclaimer=(
        "I program training, not diet. Caloric deficit drives weight loss; "
        "that's nutrition and you know it. For sharp pain or anything that "
        "doesn't feel like normal soreness, hand off to a physio."
    ),
    intake_questions=_intake,
    build_program=_build_program,
    next_session=_next_session,
    progression_rules=_progression_rules,
    world_theme="northwood",
    calibration_length=_CALIBRATION_LENGTH,
)
