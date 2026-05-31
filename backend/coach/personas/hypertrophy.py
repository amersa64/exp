"""
Hypertrophy persona — the "build muscle" goal template.

Programming logic is Upper/Lower split, 4 days/week, 8-12 rep range with
double progression. Different shape from strength: more total volume, more
isolation work, longer rep ranges, slower load progression. The aim is
muscle cross-section, not 1RM.

Per design/v2/templates/02-hypertrophy.md — MVP version:
  - Upper/Lower 4 days (no PPL 6-day variant yet — defer to v2.x)
  - No focus-muscles question yet (defer)
  - No photo block yet (defer to discipline template + composable-blocks work)
  - Same equipment branching as strength via the shared catalog ladders

This persona shares the same interface (base.Persona) as strength.py. The
engine doesn't care which persona is in play.
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


# Hypertrophy's exercise slots — broader than strength's because the split
# separates upper and lower days, leaving room for isolation work. The
# subset used during CALIBRATION is the same 5 lifts the shared battery
# probes (squat / bench / row / ohp / deadlift / pullup) — extra slots only
# come online once we transition to active phase.
_SLOT_LADDERS: dict[str, list[str]] = {
    # Compound — main movers on each day (also the calibration probes)
    "squat":         ["Barbell Squat", "Goblet Squat", "Dumbbell Squat", "Bodyweight Squat"],
    "bench":         ["Barbell Bench Press - Medium Grip", "Dumbbell Bench Press", "Pushups"],
    "row":           ["Bent Over Barbell Row", "One-Arm Dumbbell Row", "Inverted Row"],
    "deadlift":      ["Barbell Deadlift", "Stiff-Legged Dumbbell Deadlift", "Single Leg Glute Bridge"],
    "ohp":           ["Standing Military Press", "Standing Dumbbell Press", "Pushups"],
    "pullup":        ["Pullups", "Band Assisted Pull-Up", "Inverted Row"],
    "incline_press": ["Incline Dumbbell Press", "Incline Bench Press", "Pushups"],
    "pulldown":      ["Wide-Grip Lat Pulldown", "Pullups", "Inverted Row"],
    "leg_press":     ["Leg Press", "Goblet Squat", "Bodyweight Squat"],
    "leg_curl":      ["Seated Leg Curl", "Stiff-Legged Dumbbell Deadlift", "Glute Bridge"],
    "leg_ext":       ["Leg Extensions", "Bodyweight Squat", "Wall Sit"],
    # Isolation
    "lateral_raise": ["Side Lateral Raise", "Dumbbell Lateral Raise", "Pushups"],
    "curl":          ["Dumbbell Bicep Curl", "Hammer Curls", "Chin-Up"],
    "tricep":        ["Tricep Dumbbell Kickback", "Cable Pushdown", "Dips"],
    "calf":          ["Standing Dumbbell Calf Raise", "Calf Raises - With Bands", "Calf Press"],
}


_CALIBRATION_LENGTH = 5
_CALIBRATION_DAYS = lifting_calibration_days(
    _SLOT_LADDERS,
    catalog().equipment_for_profile,
)


# --- Intake (Section 4.1 stage 1) ---------------------------------------------

def _intake(prof: UserProfile | None):
    return [
        IntakeQuestion(
            "goal",
            "What do you want to do — build muscle, get stronger, lose weight, "
            "stay fit and age well, or 75-Hard-style discipline?",
        ),
        # Benchmark inputs — sex, age, bodyweight. Needed so the calibration
        # battery in week 1 can compare your numbers to other people built
        # like you. See backend/coach/calibration.py.
        IntakeQuestion(
            "sex",
            "Biological sex — male or female? (Used for strength benchmarks; "
            "they differ meaningfully by sex.)",
        ),
        IntakeQuestion(
            "age",
            "How old are you?",
            coerce=lambda s: int("".join(c for c in s if c.isdigit()) or "30"),
        ),
        IntakeQuestion(
            "bodyweight_lb",
            "What do you weigh, in lbs? (Hypertrophy progress is mostly "
            "measured relative to bodyweight.)",
            coerce=lambda s: int("".join(c for c in s if c.isdigit()) or "180"),
        ),
        IntakeQuestion(
            "experience",
            "How would you describe your training experience — none, "
            "novice (under 6 months consistent), intermediate (1+ year), or advanced?",
        ),
        IntakeQuestion(
            "days_per_week",
            "How many days per week can you train? Hypertrophy wants 4-6.",
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


# --- Programming (Section 4.1 stage 2) ----------------------------------------

# Hypertrophy starts conservative — lower loads, higher reps, more volume.
_HYPERTROPHY_DEFAULTS = {
    "squat_lb":         95,
    "bench_lb":         65,
    "deadlift_lb":      135,
    "row_lb":           65,
    "ohp_lb":           45,
    "incline_press_lb": 50,
    "leg_press_lb":     180,
    "leg_curl_lb":      60,
    "leg_ext_lb":       60,
    "lateral_raise_lb": 12,
    "curl_lb":          25,
    "tricep_lb":        25,
    "calf_lb":          45,
    "pulldown_lb":      90,
}


def _build_program(profile: UserProfile):
    """
    Start in CALIBRATION. After 5 calibration sessions we transition to the
    Upper/Lower split, 4 days/week, with double-progression on 8-12 reps —
    using observed loads, not self-reported guesses.
    """
    program = ProgramState(
        user_id=profile.user_id,
        program_name="Hypertrophy — Calibration → Upper/Lower (4x/week)",
        phase="calibration",
        calibration_index=0,
        progression={
            "day_index": 0,
            "consecutive_failed_sessions": 0,
        },
        notes=["Week 1 is calibration — five short assessments. The real "
               "Upper/Lower split starts week 2 with loads built around your "
               "actual numbers, not generic ones."],
    )

    identity_id = "pending"
    milestones = [
        Milestone(
            title="Calibration complete",
            description="Five calibration sessions logged — we know your numbers.",
            parent_identity_id=identity_id,
        ),
        Milestone(
            title="First full rep-range completion",
            description="Hit all 3 sets at 12 reps on a major lift — weight goes up.",
            parent_identity_id=identity_id,
        ),
        Milestone(
            title="4 sessions/week for 4 weeks",
            description="16 logged sessions in 4 calendar weeks — consistency milestone.",
            parent_identity_id=identity_id,
        ),
        Milestone(
            title="Squat bodyweight x8",
            description="Bodyweight squat for 8 clean reps — body-relative strength marker.",
            parent_identity_id=identity_id,
        ),
    ]
    habits = [
        Habit(
            title="Hypertrophy training",
            cadence=f"{int(profile.derived.get('days_per_week', 4))}x per week",
            parent_milestone_id=milestones[2].id,
        ),
    ]
    return program, milestones, habits


def _transition_to_active(program: ProgramState, profile: UserProfile) -> str:
    """
    Calibration complete — set starting loads from observed data (55% of est
    1RM, conservative because we'll be repping in the 8-12 range), seed the
    rep-state for each lift at 8, pick the emphasis slot, flip phase.
    """
    results = program.calibration_results
    progression = dict(program.progression)

    def load_for(slot: str, default: float) -> float:
        if slot in results:
            # Hypertrophy starts at 55% — lower than strength's 65% because
            # rep range is higher and we want headroom for double progression
            # to actually work for several weeks before we touch loads.
            return starting_load_from_calibration(results[slot], pct_of_1rm=0.55)
        return default

    progression["squat_lb"]         = load_for("squat",    _HYPERTROPHY_DEFAULTS["squat_lb"])
    progression["bench_lb"]         = load_for("bench",    _HYPERTROPHY_DEFAULTS["bench_lb"])
    progression["row_lb"]           = load_for("row",      _HYPERTROPHY_DEFAULTS["row_lb"])
    progression["deadlift_lb"]      = load_for("deadlift", _HYPERTROPHY_DEFAULTS["deadlift_lb"])
    progression["ohp_lb"]           = load_for("ohp",      _HYPERTROPHY_DEFAULTS["ohp_lb"])
    # Accessory lifts that have no direct calibration probe stay at defaults.
    progression["incline_press_lb"] = _HYPERTROPHY_DEFAULTS["incline_press_lb"]
    progression["leg_press_lb"]     = _HYPERTROPHY_DEFAULTS["leg_press_lb"]
    progression["leg_curl_lb"]      = _HYPERTROPHY_DEFAULTS["leg_curl_lb"]
    progression["leg_ext_lb"]       = _HYPERTROPHY_DEFAULTS["leg_ext_lb"]
    progression["lateral_raise_lb"] = _HYPERTROPHY_DEFAULTS["lateral_raise_lb"]
    progression["curl_lb"]          = _HYPERTROPHY_DEFAULTS["curl_lb"]
    progression["tricep_lb"]        = _HYPERTROPHY_DEFAULTS["tricep_lb"]
    progression["calf_lb"]          = _HYPERTROPHY_DEFAULTS["calf_lb"]
    progression["pulldown_lb"]      = _HYPERTROPHY_DEFAULTS["pulldown_lb"]
    # Seed double-progression rep state at the bottom of the 8-12 range.
    for slot_lb_key in _HYPERTROPHY_DEFAULTS:
        slot = slot_lb_key.replace("_lb", "")
        progression[f"reps_{slot}"] = 8

    program.progression = progression
    program.phase = "active"
    program.emphasis_slot = weakest_lift(results)

    emphasis_phrase = (f" Emphasis: {program.emphasis_slot} — that lift gets "
                       f"the extra volume for the next 4 weeks."
                       if program.emphasis_slot else "")
    starting_phrase = (f"Starting loads — squat {int(progression['squat_lb'])}, "
                       f"bench {int(progression['bench_lb'])}, "
                       f"row {int(progression['row_lb'])}, "
                       f"deadlift {int(progression['deadlift_lb'])}, "
                       f"OHP {int(progression['ohp_lb'])}. "
                       f"Rep range 8-12, double progression.")
    program.notes.append(f"Calibration complete. {starting_phrase}{emphasis_phrase}")
    return f"Calibration done. {starting_phrase}{emphasis_phrase}"


# --- Next session -------------------------------------------------------------

def _prescribe(slot: str, prog_key: str, sets: int, target_reps: int, rest: int,
               program: ProgramState, equipment: set[str | None]) -> ExercisePrescription:
    """
    Build one prescription. Loads come from progression dict; reps come from
    the per-lift reps_state (double progression). Picks the heaviest variant
    the user has equipment for.
    """
    ex: Exercise = catalog().pick_for_slot(_SLOT_LADDERS[slot], equipment)
    load = program.progression.get(prog_key) if ex.equipment in _LOADED_EQUIPMENT else None
    reps = int(program.progression.get(f"reps_{slot}", target_reps))
    cue = ex.first_instruction() or ""
    return ExercisePrescription(
        name=ex.name,
        sets=sets,
        reps=reps,
        load_lb=load,
        rest_seconds=rest,
        notes=cue[:140],
    )


def _upper_a(program: ProgramState, profile: UserProfile) -> Session:
    eq = catalog().equipment_for_profile(profile.answers.get("equipment"))
    return Session(
        name="Upper A",
        summary="Upper body — chest, back, shoulders, arms",
        exercises=[
            _prescribe("bench",         "bench_lb",         4, 8, 150, program, eq),
            _prescribe("row",           "row_lb",           4, 8, 150, program, eq),
            _prescribe("ohp",           "ohp_lb",           3, 10, 120, program, eq),
            _prescribe("pulldown",      "pulldown_lb",      3, 10, 90,  program, eq),
            _prescribe("lateral_raise", "lateral_raise_lb", 3, 12, 60,  program, eq),
            _prescribe("curl",          "curl_lb",          3, 12, 60,  program, eq),
            _prescribe("tricep",        "tricep_lb",        3, 12, 60,  program, eq),
        ],
        expected_minutes=60,
        progression_rule="Hit all sets at 12 reps → +2.5 lb upper lifts next session, reset to 8 reps.",
    )


def _lower_a(program: ProgramState, profile: UserProfile) -> Session:
    eq = catalog().equipment_for_profile(profile.answers.get("equipment"))
    return Session(
        name="Lower A",
        summary="Lower body — quads, hamstrings, glutes, calves",
        exercises=[
            _prescribe("squat",     "squat_lb",     4, 8, 150, program, eq),
            _prescribe("leg_press", "leg_press_lb", 3, 10, 120, program, eq),
            _prescribe("leg_curl",  "leg_curl_lb",  3, 10, 90,  program, eq),
            _prescribe("leg_ext",   "leg_ext_lb",   3, 12, 60,  program, eq),
            _prescribe("calf",      "calf_lb",      4, 12, 45,  program, eq),
        ],
        expected_minutes=55,
        progression_rule="Hit all sets at 12 reps → +5 lb lower lifts next session, reset to 8 reps.",
    )


def _upper_b(program: ProgramState, profile: UserProfile) -> Session:
    eq = catalog().equipment_for_profile(profile.answers.get("equipment"))
    return Session(
        name="Upper B",
        summary="Upper body — chest, back, shoulders, arms (variation)",
        exercises=[
            _prescribe("incline_press", "incline_press_lb", 4, 8, 150, program, eq),
            _prescribe("pulldown",      "pulldown_lb",      4, 8, 120, program, eq),
            _prescribe("ohp",           "ohp_lb",           3, 10, 90,  program, eq),
            _prescribe("row",           "row_lb",           3, 10, 90,  program, eq),
            _prescribe("lateral_raise", "lateral_raise_lb", 3, 12, 60,  program, eq),
            _prescribe("tricep",        "tricep_lb",        3, 12, 60,  program, eq),
            _prescribe("curl",          "curl_lb",          3, 12, 60,  program, eq),
        ],
        expected_minutes=60,
        progression_rule="Hit all sets at 12 reps → +2.5 lb upper lifts next session, reset to 8 reps.",
    )


def _lower_b(program: ProgramState, profile: UserProfile) -> Session:
    eq = catalog().equipment_for_profile(profile.answers.get("equipment"))
    return Session(
        name="Lower B",
        summary="Lower body — posterior chain focus (deadlift variation)",
        exercises=[
            _prescribe("deadlift",  "deadlift_lb",  3, 6, 180, program, eq),
            _prescribe("squat",     "squat_lb",     3, 10, 120, program, eq),
            _prescribe("leg_curl",  "leg_curl_lb",  3, 10, 90,  program, eq),
            _prescribe("leg_ext",   "leg_ext_lb",   3, 12, 60,  program, eq),
            _prescribe("calf",      "calf_lb",      4, 12, 45,  program, eq),
        ],
        expected_minutes=55,
        progression_rule="Hit all sets at 12 reps → +5 lb lower lifts next session, reset to 8 reps.",
    )


_DAYS = [_upper_a, _lower_a, _upper_b, _lower_b]


def _next_session(program: ProgramState, profile: UserProfile) -> Session:
    if program.phase == "calibration":
        idx = max(0, min(program.calibration_index, _CALIBRATION_LENGTH - 1))
        return _CALIBRATION_DAYS[idx](program, profile)
    day_index = int(program.progression.get("day_index", 0))
    builder = _DAYS[day_index % 4]
    return builder(program, profile)


# --- Adaptation (double progression) ------------------------------------------

def _progression_rules(program: ProgramState, recent_reports: list[dict]) -> tuple[ProgramState, str]:
    """
    Double progression: hit top of rep range across all sets → +load, reset reps.
    Otherwise hold load, push reps next session.

    `recent_reports`: list of {"outcome": str, "friction": str|None, "session_name": str}
    Most recent first.
    """
    if not recent_reports:
        if program.phase == "calibration":
            return program, ("Week 1 — calibration. Five sessions to learn "
                             "your numbers, then the Upper/Lower split begins.")
        return program, "First session — establishing baseline."

    p = program.model_copy(deep=True)
    latest = recent_reports[0]
    outcome = latest.get("outcome")
    session_name = latest.get("session_name", "")
    friction = latest.get("friction") or ""

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
            transition_rationale = _transition_to_active(p, profile_obj)
            return p, transition_rationale

        summary = ", ".join(recorded) if recorded else "logged"
        progress = f"{p.calibration_index}/{_CALIBRATION_LENGTH} calibration sessions done"
        return p, f"{summary}. {progress}."

    # =======================================================================
    # ACTIVE PHASE — Upper/Lower double progression (unchanged)
    # =======================================================================

    # Advance to the next day in the rotation, regardless of outcome.
    p.progression["day_index"] = (int(p.progression.get("day_index", 0)) + 1) % 4

    if outcome == "done":
        p.progression["consecutive_failed_sessions"] = 0
        # Advance rep state for each lift. MVP: we don't have per-lift rep
        # reports yet, so we advance all lifts by 1 rep, capped at 12.
        # When per-lift reporting ships in v2.x, this gets per-lift granularity.
        rationale_parts = []
        for key in list(p.progression.keys()):
            if not key.startswith("reps_"):
                continue
            slot = key[len("reps_"):]
            current_reps = int(p.progression[key])
            if current_reps >= 12:
                # Hit top of range — add weight, reset reps to 8.
                load_key = f"{slot}_lb"
                if load_key in p.progression:
                    is_lower = slot in ("squat", "deadlift", "leg_press", "leg_curl", "leg_ext", "calf")
                    bump = 5 if is_lower else 2.5
                    p.progression[load_key] = float(p.progression[load_key]) + bump
                p.progression[key] = 8
                rationale_parts.append(f"+{bump} lb {slot}")
            else:
                p.progression[key] = current_reps + 1
        rationale = ("Session done — pushing reps. " + ", ".join(rationale_parts[:3])
                     if rationale_parts else
                     "Session done — pushed one rep across lifts (still inside the 8-12 range).")

    elif outcome == "partial":
        p.progression["consecutive_failed_sessions"] = (
            int(p.progression.get("consecutive_failed_sessions", 0)) + 1
        )
        rationale = "Partial — holding load and reps. Repeat next time."

    elif outcome in ("skipped", "busy", "not_now", "ignored"):
        rationale = f"{outcome} — no change. We try again, no judgement."

    else:
        rationale = "Holding."

    # Two consecutive partials → light deload.
    if int(p.progression.get("consecutive_failed_sessions", 0)) >= 2:
        for k in list(p.progression.keys()):
            if k.endswith("_lb") and isinstance(p.progression[k], (int, float)):
                p.progression[k] = max(20.0, float(p.progression[k]) * 0.90)
        p.progression["consecutive_failed_sessions"] = 0
        rationale += " Two consecutive misses — 10% deload across all lifts."

    p.notes.append(rationale)
    return p, rationale


# --- Persona instance ---------------------------------------------------------

HYPERTROPHY_PERSONA = Persona(
    domain="hypertrophy",
    voice=(
        "You speak like a coach who programs for muscle gain — specific reps, "
        "specific loads, no hype. You name lifts and rep ranges. You never use "
        "the words 'crushed', 'beast mode', or 'gains'. You're patient about "
        "the slow pace of hypertrophy and honest that visible change takes weeks, "
        "not days. During calibration week you're an evaluator gathering data, "
        "not a hype man."
    ),
    safety_disclaimer=(
        "I program training, not medicine. Sharp pain or injury — hand off to a "
        "physio or doctor before continuing."
    ),
    intake_questions=_intake,
    build_program=_build_program,
    next_session=_next_session,
    progression_rules=_progression_rules,
    world_theme="northwood",
    calibration_length=_CALIBRATION_LENGTH,
)
