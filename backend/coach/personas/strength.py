"""
Strength persona — the "get stronger" goal template.

CALIBRATION-FIRST programming. A real strength coach doesn't hand a brand-new
client a 3x5 linear progression on day one — they assess. So our flow is:

    intake (8 questions, incl. sex/age/bodyweight for benchmarking)
       ↓
    CALIBRATION phase (week 1, 5 short structured sessions)
       - lower baseline (squat work-up)
       - upper push baseline (bench + OHP)
       - upper pull baseline (row + pullup count)
       - hinge baseline (deadlift work-up)
       - conditioning baseline (12-min walk/run)
       ↓
    benchmark engine → percentile per lift → weakest = emphasis
       ↓
    ACTIVE phase (week 2+, A/B linear progression with starting loads
                  drawn from observed data and extra volume on the
                  emphasis slot)

The active-phase logic below preserves the v1 Starting-Strength-style
progression — what changed is *where the starting loads come from* and the
fact that one slot now gets extra volume. The progression rules and deload
trigger are unchanged.

Per the "real coach" onboarding redesign (May 2026).
"""

from __future__ import annotations

from .base import IntakeQuestion, Persona
from ..calibration import (
    benchmark_user_factors,
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


# Equipment values in the catalog that imply an external load — used to decide
# whether to attach `load_lb` from the program's progression dict, or leave it
# None (bodyweight, advance via reps next iteration).
_LOADED_EQUIPMENT = {"barbell", "dumbbell", "cable", "kettlebells", "machine",
                     "e-z curl bar", "medicine ball"}


# Movement-pattern "slots" the program needs. Each slot is an ordered ladder
# of catalog names — first one the user has equipment for wins. The last
# entry in every ladder is bodyweight-available so we always have something
# prescribable (Coach Principle: always owes the user *something* to do).
_SLOT_LADDERS: dict[str, list[str]] = {
    "squat":    ["Barbell Squat", "Goblet Squat", "Dumbbell Squat", "Bodyweight Squat"],
    "bench":    ["Barbell Bench Press - Medium Grip", "Dumbbell Bench Press", "Pushups"],
    "row":      ["Bent Over Barbell Row", "One-Arm Dumbbell Row", "Inverted Row"],
    "deadlift": ["Barbell Deadlift", "Stiff-Legged Dumbbell Deadlift", "Single Leg Glute Bridge"],
    "ohp":      ["Standing Military Press", "Standing Dumbbell Press", "Pushups"],
    "pullup":   ["Pullups", "Band Assisted Pull-Up", "Inverted Row"],
}


# --- Intake (Section 4.1 stage 1) -----------------------------------------------

def _intake(prof: UserProfile | None):
    return [
        # Goal — v2 Q1. Determines which template the user lands on.
        IntakeQuestion(
            "goal",
            "What do you want to do — build muscle, get stronger, lose weight, "
            "stay fit and age well, or 75-Hard-style discipline?",
        ),
        # Three benchmark inputs. Without these we can't tell a 50-percentile
        # bench from a 90-percentile bench. The user can write "skip" for any
        # and we'll use median values for their goal — but the assessment
        # gets noticeably less useful.
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
            "What do you weigh, in lbs? (Strength is mostly measured "
            "relative to bodyweight.)",
            coerce=lambda s: int("".join(c for c in s if c.isdigit()) or "180"),
        ),
        IntakeQuestion(
            "experience",
            "How would you describe your strength-training experience — none, "
            "novice (under 6 months consistent), intermediate (1+ year), or advanced?",
        ),
        IntakeQuestion(
            "days_per_week",
            "Realistically — not aspirationally — how many days per week can you "
            "train? (2, 3, or 4)",
            coerce=lambda s: int("".join(c for c in s if c.isdigit()) or "3"),
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
            "Pick one thing you do every day without thinking — morning coffee, "
            "after-work commute, lunch break, putting the kids to bed. We'll "
            "stack training right after it.",
        ),
        IntakeQuestion(
            "training_location",
            "Where will the training actually happen? (e.g. 'the gym down the "
            "street', 'the garage', 'the living room')",
        ),
    ]


# --- Programming (Section 4.1 stage 2) -----------------------------------------

_NOVICE_DEFAULTS = {
    "squat_lb": 95,
    "bench_lb": 65,
    "deadlift_lb": 135,
    "row_lb": 65,
    "ohp_lb": 45,
}

# How many calibration sessions before we transition to the active program.
_CALIBRATION_LENGTH = 5


def _build_program(profile: UserProfile):
    """
    A fresh program always starts in CALIBRATION. The active-phase progression
    dict gets filled in later (when the persona transitions to active in
    progression_rules), using observed numbers — not guessed defaults.

    We still seed minimal scaffolding in progression so unrelated code paths
    (debug pane, journal serialization) don't blow up reading the dict.
    """
    program = ProgramState(
        user_id=profile.user_id,
        program_name="Strength — Calibration → Linear Progression",
        phase="calibration",
        calibration_index=0,
        progression={
            "ab_toggle": 0,
            "consecutive_easy_sessions": 0,
            "consecutive_failed_sessions": 0,
        },
        notes=["Week 1 is calibration — five short sessions that tell me "
               "where you actually are. The real program starts week 2 with "
               "loads built around your numbers, not generic ones."],
    )

    identity_id = "pending"  # set by the engine when the Identity is created
    milestones = [
        Milestone(
            title="Calibration complete",
            description="Five calibration sessions logged — we know your numbers.",
            parent_identity_id=identity_id,
        ),
        Milestone(
            title="Squat bodyweight x5",
            description="Squat your bodyweight for 5 clean reps.",
            parent_identity_id=identity_id,
        ),
        Milestone(
            title="3 sessions/week for 4 weeks",
            description="12 logged sessions in 4 calendar weeks — consistency milestone.",
            parent_identity_id=identity_id,
        ),
        Milestone(
            title="Squat 1.5x bodyweight x5",
            description="Long-horizon strength marker for novice → intermediate.",
            parent_identity_id=identity_id,
        ),
    ]
    habits = [
        Habit(
            title="Strength training",
            cadence=f"{int(profile.derived.get('days_per_week', 3))}x per week",
            parent_milestone_id=milestones[2].id,
        ),
    ]
    return program, milestones, habits


# --- Calibration sessions ------------------------------------------------------
#
# Uses the shared lifting-calibration battery from ../calibration.py — same
# 5 sessions (lower, upper push, upper pull, hinge, conditioning) as hypertrophy
# and discipline. What changes per persona is the starting-load policy when
# we transition to active phase, not the assessment itself.

_CALIBRATION_DAYS = lifting_calibration_days(
    _SLOT_LADDERS,
    catalog().equipment_for_profile,
)


# --- Active-phase sessions -----------------------------------------------------

def _prescribe(slot: str, prog_key: str, sets: int, reps: int, rest: int,
               program: ProgramState, equipment: set[str | None]) -> ExercisePrescription:
    """
    Build one active-phase prescription. Picks the heaviest variant the user
    has equipment for; loads from the program's progression dict only when
    the resolved exercise is actually loaded.
    """
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


def _emphasis_sets(slot: str, program: ProgramState, base: int) -> int:
    """Weakest lift identified during calibration gets +1 set of volume."""
    return base + 1 if program.emphasis_slot == slot else base


def _session_a(program: ProgramState, profile: UserProfile) -> Session:
    eq = catalog().equipment_for_profile(profile.answers.get("equipment"))
    return Session(
        name="Workout A",
        summary="Full body — quads, chest, mid-back",
        exercises=[
            _prescribe("squat", "squat_lb", _emphasis_sets("squat", program, 3), 5, 180, program, eq),
            _prescribe("bench", "bench_lb", _emphasis_sets("bench", program, 3), 5, 150, program, eq),
            _prescribe("row",   "row_lb",   _emphasis_sets("row",   program, 3), 5, 120, program, eq),
        ],
        expected_minutes=45,
        progression_rule="If completed: +10 lb squat / +5 lb upper next session.",
    )


def _session_b(program: ProgramState, profile: UserProfile) -> Session:
    eq = catalog().equipment_for_profile(profile.answers.get("equipment"))
    return Session(
        name="Workout B",
        summary="Full body — quads, shoulders, posterior chain",
        exercises=[
            _prescribe("squat",    "squat_lb",    _emphasis_sets("squat",    program, 3), 5, 180, program, eq),
            _prescribe("ohp",      "ohp_lb",      _emphasis_sets("ohp",      program, 3), 5, 150, program, eq),
            _prescribe("deadlift", "deadlift_lb", _emphasis_sets("deadlift", program, 1), 5, 180, program, eq),
        ],
        expected_minutes=40,
        progression_rule="If completed: +10 lb squat / +5 lb OHP / +10 lb deadlift next session.",
    )


def _next_session(program: ProgramState, profile: UserProfile) -> Session:
    if program.phase == "calibration":
        idx = max(0, min(program.calibration_index, _CALIBRATION_LENGTH - 1))
        return _CALIBRATION_DAYS[idx](program, profile)
    return (
        _session_a(program, profile)
        if program.progression.get("ab_toggle", 0) == 0
        else _session_b(program, profile)
    )


# --- Adaptation (Section 4.1 stage 6) -----------------------------------------

def _transition_to_active(program: ProgramState, profile: UserProfile) -> str:
    """
    Calibration complete — derive starting loads from observed data, pick
    the emphasis slot (weakest lift), flip phase to active.
    """
    results = program.calibration_results
    progression = dict(program.progression)

    def load_for(slot: str, default: float) -> float:
        if slot in results:
            return starting_load_from_calibration(results[slot])
        return default

    progression["squat_lb"]    = load_for("squat",    _NOVICE_DEFAULTS["squat_lb"])
    progression["bench_lb"]    = load_for("bench",    _NOVICE_DEFAULTS["bench_lb"])
    progression["row_lb"]      = load_for("row",      _NOVICE_DEFAULTS["row_lb"])
    progression["deadlift_lb"] = load_for("deadlift", _NOVICE_DEFAULTS["deadlift_lb"])
    progression["ohp_lb"]      = load_for("ohp",      _NOVICE_DEFAULTS["ohp_lb"])
    progression["ab_toggle"] = 0

    program.progression = progression
    program.phase = "active"
    program.emphasis_slot = weakest_lift(results)

    emphasis_phrase = (f" Emphasis: {program.emphasis_slot} — extra set per "
                       f"session for the next 4 weeks."
                       if program.emphasis_slot else "")
    starting_phrase = (f"Starting loads — squat {int(progression['squat_lb'])}, "
                       f"bench {int(progression['bench_lb'])}, "
                       f"deadlift {int(progression['deadlift_lb'])}, "
                       f"OHP {int(progression['ohp_lb'])}, "
                       f"row {int(progression['row_lb'])}.")
    program.notes.append(f"Calibration complete. {starting_phrase}{emphasis_phrase}")
    return f"Calibration done. {starting_phrase}{emphasis_phrase}"


def _progression_rules(program: ProgramState, recent_reports: list[dict]) -> tuple[ProgramState, str]:
    """
    Two distinct progression policies depending on phase.

    Calibration:
      - record the top_sets from the latest report into calibration_results
      - increment calibration_index
      - on the last calibration session, transition to active phase
      - never change a load mid-calibration

    Active: linear progression as before, with deload on consecutive misses.
    """
    if not recent_reports:
        if program.phase == "calibration":
            return program, ("Week 1 — calibration. Five sessions to learn "
                             "your numbers, then the real program starts.")
        return program, "No reports yet — first session is a baseline."

    p = program.model_copy(deep=True)
    latest = recent_reports[0]
    outcome = latest.get("outcome")
    friction = latest.get("friction") or ""

    # =======================================================================
    # CALIBRATION PHASE
    # =======================================================================
    if p.phase == "calibration":
        # Profile lookup needs the caller to pass it in via the report dict.
        # The lifecycle.adapt() construction includes "profile" in newer
        # versions; older callers won't. We tolerate both.
        profile_obj: UserProfile | None = latest.get("profile")
        top_sets = latest.get("top_sets") or {}

        # Persist top sets ONLY if we have a profile to benchmark against.
        # Without it we still advance the calibration index — partial data
        # is fine — but we skip the percentile derivation.
        recorded: list[str] = []
        if profile_obj is not None and top_sets:
            recorded = record_top_sets(p, profile_obj, top_sets)

        # Advance the calibration cursor unless the user actually skipped.
        if outcome in ("done", "partial"):
            p.calibration_index = min(p.calibration_index + 1, _CALIBRATION_LENGTH)
        # "skipped" / "busy" / "not_now" / "ignored" → cursor holds; we re-present
        # the same calibration session next time.

        # Transition?
        if p.calibration_index >= _CALIBRATION_LENGTH and profile_obj is not None:
            transition_rationale = _transition_to_active(p, profile_obj)
            return p, transition_rationale

        summary = ", ".join(recorded) if recorded else "logged"
        progress = f"{p.calibration_index}/{_CALIBRATION_LENGTH} calibration sessions done"
        return p, f"{summary}. {progress}."

    # =======================================================================
    # ACTIVE PHASE (unchanged from v1 linear progression)
    # =======================================================================
    session_name = latest.get("session_name", "")
    is_a = "A" in session_name

    rationale: str
    if outcome == "done":
        p.progression["consecutive_failed_sessions"] = 0
        if is_a:
            p.progression["squat_lb"] += 10
            p.progression["bench_lb"] += 5
            p.progression["row_lb"]   += 5
            rationale = "Last session completed → +10 squat, +5 bench, +5 row."
        else:
            p.progression["squat_lb"] += 10
            p.progression["ohp_lb"]   += 5
            p.progression["deadlift_lb"] += 10
            rationale = "Last session completed → +10 squat, +5 OHP, +10 deadlift."
        if friction.lower().startswith("too easy"):
            p.progression["consecutive_easy_sessions"] = (
                p.progression.get("consecutive_easy_sessions", 0) + 1
            )
        else:
            p.progression["consecutive_easy_sessions"] = 0

    elif outcome == "partial":
        rationale = "Partial completion — holding loads. Repeat this session next time."

    elif outcome in ("skipped", "busy", "not_now", "ignored"):
        rationale = f"Session was {outcome} — no progression. We'll try again, no judgement."

    else:
        rationale = "No clear signal — holding loads."

    if outcome == "partial":
        p.progression["consecutive_failed_sessions"] = (
            p.progression.get("consecutive_failed_sessions", 0) + 1
        )
    if p.progression.get("consecutive_failed_sessions", 0) >= 2:
        for k in ("squat_lb", "bench_lb", "deadlift_lb", "ohp_lb", "row_lb"):
            current = p.progression.get(k, _NOVICE_DEFAULTS.get(k, 45))
            p.progression[k] = max(45, round(current * 0.9 / 5) * 5)
        p.progression["consecutive_failed_sessions"] = 0
        rationale += " Two consecutive misses → 10% deload across the board to rebuild momentum."

    p.progression["ab_toggle"] = 1 - p.progression.get("ab_toggle", 0)
    p.session_index += 1
    p.notes.append(rationale)
    return p, rationale


# --- Persona instance ---------------------------------------------------------

STRENGTH_PERSONA = Persona(
    domain="strength",
    voice=(
        "You speak like a strength coach who has actually programmed for novices — "
        "direct, technical when it matters, never preachy. You name lifts, weights, "
        "and reps. You never use the word 'journey'. You never moralize. "
        "If the user is tired or busy, you shrink the ask before you increase it. "
        "During calibration week you sound like an experienced coach gathering "
        "data, not a hype man — 'we're learning where you are, not testing your "
        "ego'. After calibration you reference their actual numbers."
    ),
    safety_disclaimer=(
        "I coach training, not medicine. For sharp pain, injury, or anything that "
        "doesn't feel like normal soreness, I'll hand off to a physio or doctor."
    ),
    intake_questions=_intake,
    build_program=_build_program,
    next_session=_next_session,
    progression_rules=_progression_rules,
    world_theme="northwood",
    calibration_length=_CALIBRATION_LENGTH,
)
