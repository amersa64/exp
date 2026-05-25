"""
Fitness / Strength & Conditioning persona — v1's one and only domain.

Programming logic is a deliberately conservative linear progression for a novice,
in the spirit of Starting Strength / GZCLP. It is REAL programming, not theatre:
specific lifts, specific load progression rules, deload triggers, exactly what
Rubric B2 and B4 demand. A real strength coach will not flinch.

Section 11 anti-pattern guardrails respected:
  - No "30 min workout" — every prescription names the lift, sets, reps, load.
  - Programming adapts on report (see progression_rules) — not static slop.

Add more sophistication when a real user outgrows this. Do not over-engineer now.
"""

from __future__ import annotations

from .base import IntakeQuestion, Persona
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
    "press":    ["Barbell Bench Press - Medium Grip", "Dumbbell Bench Press", "Pushups"],
    "row":      ["Bent Over Barbell Row", "One-Arm Dumbbell Row", "Inverted Row"],
    "deadlift": ["Barbell Deadlift", "Stiff-Legged Dumbbell Deadlift", "Single Leg Glute Bridge"],
    "ohp":      ["Standing Military Press", "Standing Dumbbell Press", "Pushups"],
}


# --- Intake (Section 4.1 stage 1) -----------------------------------------------

def _intake(prof: UserProfile | None):
    return [
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
            "baseline_squat",
            "Roughly — most you can squat for 5 reps with good form? (lb, or 'unsure')",
            coerce=lambda s: int("".join(c for c in s if c.isdigit()) or "0") or "unsure",
        ),
        # Atomic Habits ch.5: habit stacking — anchor the new behavior to
        # something you already do every day without fail.
        IntakeQuestion(
            "anchor_habit",
            "Pick one thing you do every day without thinking — morning coffee, "
            "after-work commute, lunch break, putting the kids to bed. We'll "
            "stack training right after it.",
        ),
        # Where the session will actually happen — fuels implementation
        # intentions and reduces decision friction at game time.
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


def _build_program(profile: UserProfile):
    """Linear progression, A/B alternating, 3 days/week default."""
    derived = profile.derived

    squat = int(derived.get("1rm_squat_lb", _NOVICE_DEFAULTS["squat_lb"]) or _NOVICE_DEFAULTS["squat_lb"])
    # Start working sets ~70% of reported 5RM, then add weight each session.
    progression = {
        "squat_lb": max(45, round(squat * 0.7 / 5) * 5),
        "bench_lb": _NOVICE_DEFAULTS["bench_lb"],
        "deadlift_lb": _NOVICE_DEFAULTS["deadlift_lb"],
        "row_lb": _NOVICE_DEFAULTS["row_lb"],
        "ohp_lb": _NOVICE_DEFAULTS["ohp_lb"],
        "consecutive_easy_sessions": 0,
        "consecutive_failed_sessions": 0,
        "ab_toggle": 0,  # 0 = A next, 1 = B next
    }

    program = ProgramState(
        user_id=profile.user_id,
        program_name="Linear Progression — Novice (A/B, 3x/week)",
        progression=progression,
        notes=["Add 5 lb upper / 10 lb lower per successful session until a miss; "
               "on a miss, repeat the load; two misses in a row = 10% deload."],
    )

    # Hierarchy: Identity → Milestones → Habits → (actions are minted per session)
    identity_id = "pending"  # set by the engine when the Identity is created
    milestones = [
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
            cadence=f"{int(derived.get('days_per_week', 3))}x per week",
            parent_milestone_id=milestones[1].id,
        ),
    ]
    return program, milestones, habits


# --- Next session (Section 4.1 stage 3 content) --------------------------------

def _prescribe(slot: str, prog_key: str, sets: int, reps: int, rest: int,
               program: ProgramState, equipment: set[str | None]) -> ExercisePrescription:
    """
    Build one prescription from the catalog. Picks the heaviest variant the
    user has equipment for; loads from the program's progression dict only
    when the resolved exercise is actually loaded (skips for bodyweight).
    The first coaching cue from the catalog rides along as `notes`.
    """
    ex: Exercise = catalog().pick_for_slot(_SLOT_LADDERS[slot], equipment)
    load = program.progression.get(prog_key) if ex.equipment in _LOADED_EQUIPMENT else None
    # Pull one concrete cue from the dataset rather than authoring a generic
    # one — these are the strings a real strength coach would say at the bar.
    cue = ex.first_instruction() or ""
    return ExercisePrescription(
        name=ex.name,
        sets=sets,
        reps=reps,
        load_lb=load,
        rest_seconds=rest,
        notes=cue[:140],
    )


def _session_a(program: ProgramState, profile: UserProfile) -> Session:
    eq = catalog().equipment_for_profile(profile.answers.get("equipment"))
    return Session(
        name="Lower A",
        exercises=[
            _prescribe("squat", "squat_lb", 3, 5, 180, program, eq),
            _prescribe("press", "bench_lb", 3, 5, 150, program, eq),
            _prescribe("row",   "row_lb",   3, 5, 120, program, eq),
        ],
        expected_minutes=45,
        progression_rule="If completed: +10 lb squat / +5 lb upper next session.",
    )


def _session_b(program: ProgramState, profile: UserProfile) -> Session:
    eq = catalog().equipment_for_profile(profile.answers.get("equipment"))
    return Session(
        name="Lower B",
        exercises=[
            _prescribe("squat",    "squat_lb",    3, 5, 180, program, eq),
            _prescribe("ohp",      "ohp_lb",      3, 5, 150, program, eq),
            _prescribe("deadlift", "deadlift_lb", 1, 5, 180, program, eq),
        ],
        expected_minutes=40,
        progression_rule="If completed: +10 lb squat / +5 lb OHP / +10 lb deadlift next session.",
    )


def _next_session(program: ProgramState, profile: UserProfile) -> Session:
    return (
        _session_a(program, profile)
        if program.progression.get("ab_toggle", 0) == 0
        else _session_b(program, profile)
    )


# --- Adaptation (Section 4.1 stage 6) -----------------------------------------

def _progression_rules(program: ProgramState, recent_reports: list[dict]) -> tuple[ProgramState, str]:
    """
    The thing that makes us a coach, not a plan generator (Rubric B3).

    `recent_reports` is a list of {"outcome": NudgeOutcome.value, "friction": str|None,
                                   "session_name": str}. The most recent first.
    """
    if not recent_reports:
        return program, "No reports yet — first session is a baseline."

    latest = recent_reports[0]
    outcome = latest.get("outcome")
    session_name = latest.get("session_name", "")
    is_lower_a = "A" in session_name

    p = program.model_copy(deep=True)
    rationale: str

    if outcome == "done":
        p.progression["consecutive_failed_sessions"] = 0
        # Hooke's law of novice progression: add load.
        if is_lower_a:
            p.progression["squat_lb"] += 10
            p.progression["bench_lb"] += 5
            p.progression["row_lb"] += 5
            rationale = "Last session completed → +10 squat, +5 bench, +5 row."
        else:
            p.progression["squat_lb"] += 10
            p.progression["ohp_lb"] += 5
            p.progression["deadlift_lb"] += 10
            rationale = "Last session completed → +10 squat, +5 OHP, +10 deadlift."
        # Was it "too easy"? Bump consecutive_easy and consider faster jumps later.
        if (latest.get("friction") or "").lower().startswith("too easy"):
            p.progression["consecutive_easy_sessions"] += 1
        else:
            p.progression["consecutive_easy_sessions"] = 0

    elif outcome == "partial":
        # Hold the load; do not progress. Note the friction.
        rationale = "Partial completion — holding loads. Repeat this session next time."

    elif outcome in ("skipped", "busy", "not_now", "ignored"):
        # Hold the program — no punishment.
        rationale = f"Session was {outcome} — no progression. We'll try again, no judgement."

    else:
        rationale = "No clear signal — holding loads."

    # Two consecutive failed-to-progress signals = deload.
    if outcome in ("partial",):
        p.progression["consecutive_failed_sessions"] = p.progression.get("consecutive_failed_sessions", 0) + 1
    if p.progression["consecutive_failed_sessions"] >= 2:
        for k in ("squat_lb", "bench_lb", "deadlift_lb", "ohp_lb", "row_lb"):
            p.progression[k] = max(45 if "lb" in k else 0, round(p.progression[k] * 0.9 / 5) * 5)
        p.progression["consecutive_failed_sessions"] = 0
        rationale += " Two consecutive misses → 10% deload across the board to rebuild momentum."

    # Toggle A/B for next session.
    p.progression["ab_toggle"] = 1 - p.progression.get("ab_toggle", 0)
    p.session_index += 1
    p.notes.append(rationale)
    return p, rationale


# --- Persona instance ---------------------------------------------------------

FITNESS_PERSONA = Persona(
    domain="fitness",
    voice=(
        "You speak like a strength coach who has actually programmed for novices — "
        "direct, technical when it matters, never preachy. You name lifts, weights, "
        "and reps. You never use the word 'journey'. You never moralize. "
        "If the user is tired or busy, you shrink the ask before you increase it."
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
)
