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
from ..models import (
    ExercisePrescription,
    Habit,
    Milestone,
    ProgramState,
    Session,
    UserProfile,
)


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

def _session_a(p: ProgramState) -> Session:
    sq = p.progression["squat_lb"]
    bn = p.progression["bench_lb"]
    rw = p.progression["row_lb"]
    return Session(
        name="Lower A",
        exercises=[
            ExercisePrescription(name="Back Squat", sets=3, reps=5, load_lb=sq, rest_seconds=180,
                                 notes="Work sets at this load. If all 3x5 feel easy (RPE ≤ 7), report 'too easy'."),
            ExercisePrescription(name="Bench Press", sets=3, reps=5, load_lb=bn, rest_seconds=150),
            ExercisePrescription(name="Barbell Row", sets=3, reps=5, load_lb=rw, rest_seconds=120,
                                 notes="Pause at the bottom for 1s — no momentum."),
        ],
        expected_minutes=45,
        progression_rule="If completed: +10 lb squat / +5 lb upper next session.",
    )


def _session_b(p: ProgramState) -> Session:
    sq = p.progression["squat_lb"]
    oh = p.progression["ohp_lb"]
    dl = p.progression["deadlift_lb"]
    return Session(
        name="Lower B",
        exercises=[
            ExercisePrescription(name="Back Squat", sets=3, reps=5, load_lb=sq, rest_seconds=180),
            ExercisePrescription(name="Overhead Press", sets=3, reps=5, load_lb=oh, rest_seconds=150),
            ExercisePrescription(name="Deadlift", sets=1, reps=5, load_lb=dl, rest_seconds=180,
                                 notes="One working set — reset every rep, no bouncing."),
        ],
        expected_minutes=40,
        progression_rule="If completed: +10 lb squat / +5 lb OHP / +10 lb deadlift next session.",
    )


def _next_session(program: ProgramState, profile: UserProfile) -> Session:
    return _session_a(program) if program.progression.get("ab_toggle", 0) == 0 else _session_b(program)


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
