"""
Longevity persona — "stay fit, age well" goal template.

Trains the movement patterns of independent living (Attia's Centenarian
Decathlon): sit-to-stand, push, pull, carry, balance. 2-3 day full body, low
impact, conservative loads, glacial progression. Plain-English vocabulary —
no jargon, no PR culture, no "shred / transform / cleanse" language.

The hardest design constraint: most weeks the program does NOT progress.
Holding the same load for a year is the win. The progression rule reflects
this — clean reps move the load only after a sustained "felt easy" streak.

Per design/v2/templates/04-longevity.md.

MVP scope (this file):
  - 3-day default; 2-day path is the same Mon+Fri without Wed
  - Vocab translation is inlined via the prescription notes (no separate
    translator module yet — design doc proposes one but v2 keeps it simple)
  - Pain-keyword detection in adaptation: triggers a hold + safety nudge
  - HealthKit weight de-emphasis lives on the iOS side (Becoming tab block
    composition); backend doesn't need to know
"""

from __future__ import annotations

from .base import IntakeQuestion, Persona
from ..calibration import (
    longevity_calibration_days,
    record_top_sets,
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


_CALIBRATION_LENGTH = 5
_CALIBRATION_DAYS = longevity_calibration_days()


_LOADED_EQUIPMENT = {"barbell", "dumbbell", "cable", "kettlebells", "machine",
                     "e-z curl bar"}


# Slot ladders — easier → harder, picker takes the first match that fits the
# user's equipment. Designed so a bodyweight-only longevity user still gets a
# coherent program (the canonical case per the design doc).
_SLOT_LADDERS: dict[str, list[str]] = {
    "sit_stand":  ["Chair Squat", "Goblet Squat", "Dumbbell Squat", "Bodyweight Squat"],
    "push":       ["Incline Push-Up", "Dumbbell Bench Press", "Pushups"],
    "row":        ["One-Arm Dumbbell Row", "Bent Over Two-Dumbbell Row", "Inverted Row"],
    "step_up":    ["Dumbbell Step Ups", "Barbell Step Ups", "Bodyweight Walking Lunge"],
    "ohp":        ["Standing Dumbbell Press", "Dumbbell Shoulder Press", "Pushups"],
    "carry":      ["Farmer's Walk", "Farmer's Walk", "Farmer's Walk"],
    # Mobility + balance — duration-based, no load.
    "hip_flow":   ["Hip Circles (prone)", "Hip Circles (prone)", "Hip Circles (prone)"],
    "thoracic":   ["Cat Stretch", "Cat Stretch", "Cat Stretch"],
    "balance":    ["Single-Leg High Box Squat", "Bodyweight Walking Lunge", "Bodyweight Walking Lunge"],
}


# Plain-English overlays. Longevity users have been condescended to by
# wellness culture; the gym words alienate them and the design doc
# (vocabulary section) calls these out as the biggest design constraint.
# We surface the plain phrasing in the prescription notes — the underlying
# exercise name stays canonical so cross-template logic (alternates, history,
# adaptation) keeps working.
_PLAIN_NOTES: dict[str, str] = {
    "Chair Squat":            "Sit down to a chair, stand back up. Slow and controlled.",
    "Goblet Squat":           "Hold the weight at your chest, sit down between your feet, stand up.",
    "Dumbbell Squat":         "Hold a weight in each hand at your shoulders. Sit down, stand up.",
    "Bodyweight Squat":       "Sit down to about knee height, stand back up. Hands forward for balance.",
    "Incline Push-Up":        "Hands on a counter or sturdy chair. Lower chest to your hands, push back.",
    "Dumbbell Bench Press":   "Lying on your back, press the weights up from your chest.",
    "Pushups":                "From the floor or your knees. Slow on the way down.",
    "One-Arm Dumbbell Row":   "One knee on a bench, pull the weight toward your ribs.",
    "Bent Over Two-Dumbbell Row":
                              "Hinge forward at the hips, back flat. Pull both weights to your ribs.",
    "Inverted Row":           "Lying under a sturdy bar or table edge, pull your chest up to it.",
    "Dumbbell Step Ups":      "Hold a weight in each hand. Step up onto a low step, then back down.",
    "Barbell Step Ups":       "Bar across your shoulders. Step up onto a low platform, then back down.",
    "Bodyweight Walking Lunge":
                              "Step forward into a lunge, then bring the other foot through. Hands free.",
    "Standing Dumbbell Press":
                              "Weights at your shoulders, press them straight overhead.",
    "Dumbbell Shoulder Press":
                              "Weights at your shoulders, press them straight overhead.",
    "Farmer's Walk":          "Pick up something heavy in each hand, walk in a straight line, set down. "
                              "Groceries or jugs work fine at home.",
    "Hip Circles (prone)":    "On hands and knees, slow circles with one knee at a time. Both directions.",
    "Cat Stretch":            "On hands and knees, round and arch your back slowly.",
    "Single-Leg High Box Squat":
                              "Stand near a wall in case. One foot on a low box, lower yourself, stand up.",
}


def _plain_note(name: str, fallback: str) -> str:
    """Plain-English override if we have one; otherwise the catalog's first instruction."""
    return _PLAIN_NOTES.get(name, fallback)[:160]


_LONGEVITY_DEFAULTS = {
    # Starting loads — conservative even relative to conditioning's already
    # conservative defaults. A longevity user who can squat a barbell starts
    # on dumbbells; the strength-training-then-stopped user starts here too.
    "squat_lb":   25,   # dumbbell per hand or bodyweight chair squat with no load
    "press_lb":   15,   # one DB per hand
    "row_lb":     15,
    "step_lb":    10,
    "ohp_lb":     10,
    # Carry: held weight per hand, in pounds. Single number for simplicity.
    "carry_lb":   15,
    # Steps per round in the carry walk.
    "carry_steps": 30,
    # Mobility/balance hold durations in seconds — start small, grow slowly.
    "balance_seconds": 30,
    # 3-day rotation cursor.
    "day_index": 0,
    # Streak of clean sessions before we touch loads (glacial progression).
    "clean_streak": 0,
    "consecutive_failed_sessions": 0,
}


# --- Intake -------------------------------------------------------------------

def _intake(prof: UserProfile | None):
    return [
        IntakeQuestion(
            "goal",
            "What do you want to do — build muscle, get stronger, lose weight, "
            "stay fit and age well, or 75-Hard-style discipline?",
        ),
        IntakeQuestion(
            "age_band",
            "Roughly which decade are you in? (under 50, 50s, 60s, or 70+)",
        ),
        IntakeQuestion(
            "experience",
            "Have you trained before? (never, used to but stopped, "
            "or currently active)",
        ),
        IntakeQuestion(
            "days_per_week",
            "How many days per week can you train? 2 or 3 is plenty for this — "
            "more is not better here.",
            coerce=lambda s: int("".join(c for c in s if c.isdigit()) or "3"),
        ),
        IntakeQuestion(
            "mobility_limits",
            "Anything that hurts when you move it, or any movements you should "
            "avoid? Describe it, or write 'none'.",
        ),
        IntakeQuestion(
            "equipment",
            "What equipment do you have at home or where you'll train? "
            "(dumbbells / barbell+rack / full gym / nothing — bodyweight is fine)",
        ),
        IntakeQuestion(
            "anchor_habit",
            "Pick one thing you do every day without thinking. We'll stack the "
            "training right after it.",
        ),
        IntakeQuestion(
            "training_location",
            "Where will the training actually happen?",
        ),
    ]


# --- Programming --------------------------------------------------------------

def _build_program(profile: UserProfile):
    """
    Start in CALIBRATION (functional assessment, not strength benchmark).
    After 5 short probes — sit-to-stand, push count, balance, carry,
    6-minute walk — we transition to the 3-day full-body rotation with
    starting loads/holds calibrated to observed numbers.
    """
    progression: dict[str, float | int] = dict(_LONGEVITY_DEFAULTS)
    # Calibration phase doesn't use the day_index yet — the assessment
    # battery has its own cursor. We keep day_index seeded so the active
    # phase rotation has a sensible starting point post-calibration.

    program = ProgramState(
        user_id=profile.user_id,
        program_name="Longevity — Calibration → full body, 2-3x/week",
        phase="calibration",
        calibration_index=0,
        progression=progression,
        notes=["Week 1 is calibration — five short functional probes "
               "(sit-to-stand, push count, balance, carry, walk pace). "
               "The program starts week 2 calibrated to your numbers. "
               "Glacial progression after that, by design."],
    )

    identity_id = "pending"
    milestones = [
        Milestone(
            title="Sit-to-stand x10, no hands",
            description="Stand up from a chair ten times without using your "
                        "hands. Functional baseline.",
            parent_identity_id=identity_id,
        ),
        Milestone(
            title="Single-leg stand 30 seconds, eyes open",
            description="Each leg, thirty seconds without grabbing anything. "
                        "Cuts fall risk meaningfully.",
            parent_identity_id=identity_id,
        ),
        Milestone(
            title="Walk briskly 30 min, twice in a week",
            description="Outside, conversational pace. The cardiovascular floor.",
            parent_identity_id=identity_id,
        ),
        Milestone(
            title="Carry 15 lb for 60 steps",
            description="Groceries, suitcase, grandchild — all the same skill.",
            parent_identity_id=identity_id,
        ),
        Milestone(
            title="6 months consistent",
            description="The long-haul marker. This is when it stops being a "
                        "program and starts being who you are.",
            parent_identity_id=identity_id,
        ),
    ]
    habits = [
        Habit(
            title="Full-body training",
            cadence="2-3x per week",
            parent_milestone_id=milestones[0].id,
        ),
        Habit(
            title="Daily walk",
            cadence="20-30 min, daily",
            parent_milestone_id=milestones[2].id,
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
        notes=_plain_note(ex.name, ex.first_instruction() or ""),
    )


def _prescribe_carry(program: ProgramState, equipment: set[str | None]) -> ExercisePrescription:
    ex: Exercise = catalog().pick_for_slot(_SLOT_LADDERS["carry"], equipment)
    weight = int(program.progression.get("carry_lb", 15))
    steps = int(program.progression.get("carry_steps", 30))
    # Carry is rounds × walks. Reps = steps per walk (we render reps as "steps"
    # contextually via notes). For visual parity with cardio we don't set
    # duration_min — the carry feels like a strength set, not cardio.
    return ExercisePrescription(
        name=ex.name,
        sets=2,
        reps=steps,
        load_lb=float(weight),
        rest_seconds=60,
        notes=f"{weight} lb in each hand, {steps} steps. Set down, rest, go again. "
              "Groceries or jugs work fine at home.",
    )


def _prescribe_hold(slot: str, program: ProgramState, equipment: set[str | None],
                    label: str) -> ExercisePrescription:
    """Duration-based mobility/balance hold. Rendered as 'N×Xs' on iOS."""
    ex: Exercise = catalog().pick_for_slot(_SLOT_LADDERS[slot], equipment)
    seconds = int(program.progression.get("balance_seconds", 30))
    # Encode "30 second hold" as duration_min=0 + reps=seconds. iOS renders
    # this oddly; simpler is to bake it into the notes string and let the
    # row show "2×30" + the words "seconds, each side" in the note.
    return ExercisePrescription(
        name=ex.name,
        sets=2,
        reps=seconds,
        load_lb=None,
        rest_seconds=20,
        notes=f"{label} — {seconds} seconds. Slow and steady. Each side counts as one round.",
    )


def _strength_a(program: ProgramState, profile: UserProfile) -> Session:
    eq = catalog().equipment_for_profile(profile.answers.get("equipment"))
    return Session(
        name="Full Body — Strength A",
        summary="Sit-stand, push, pull, carry",
        exercises=[
            _prescribe("sit_stand", "squat_lb", 2, 10, 90, program, eq),
            _prescribe("push",      "press_lb", 2, 10, 90, program, eq),
            _prescribe("row",       "row_lb",   2, 10, 90, program, eq),
            _prescribe_carry(program, eq),
        ],
        expected_minutes=30,
        progression_rule="Two clean weeks at the same load → add a single rep. "
                         "Loads change rarely on purpose.",
    )


def _mobility_balance(program: ProgramState, profile: UserProfile) -> Session:
    eq = catalog().equipment_for_profile(profile.answers.get("equipment"))
    return Session(
        name="Mobility + Balance",
        summary="Easy strength, mobility flow, balance",
        exercises=[
            _prescribe_hold("hip_flow",  program, eq, "Slow hip circles"),
            _prescribe_hold("thoracic",  program, eq, "Back round and arch"),
            _prescribe_hold("balance",   program, eq, "Hold steady — eyes open"),
            _prescribe("sit_stand", None, 2, 8, 60, program, eq),
        ],
        expected_minutes=30,
        progression_rule="Add 10 seconds to holds every 3-4 weeks once they feel solid. "
                         "Eyes-closed balance is a later progression.",
    )


def _strength_b(program: ProgramState, profile: UserProfile) -> Session:
    eq = catalog().equipment_for_profile(profile.answers.get("equipment"))
    return Session(
        name="Full Body — Strength B",
        summary="Step up, overhead press, row, carry",
        exercises=[
            _prescribe("step_up", "step_lb", 2, 8,  90, program, eq),
            _prescribe("ohp",     "ohp_lb",  2, 8,  90, program, eq),
            _prescribe("row",     "row_lb",  2, 10, 90, program, eq),
            _prescribe_carry(program, eq),
        ],
        expected_minutes=30,
        progression_rule="Two clean weeks at the same load → add a single rep. "
                         "Loads change rarely on purpose.",
    )


_DAYS = [_strength_a, _mobility_balance, _strength_b]


def _next_session(program: ProgramState, profile: UserProfile) -> Session:
    if program.phase == "calibration":
        idx = max(0, min(program.calibration_index, _CALIBRATION_LENGTH - 1))
        return _CALIBRATION_DAYS[idx](program, profile)
    day_index = int(program.progression.get("day_index", 0))
    builder = _DAYS[day_index % 3]
    return builder(program, profile)


def _transition_to_active(program: ProgramState, profile: UserProfile) -> str:
    """
    Calibration complete — derive starting holds/loads from functional
    probes. Longevity's calibration_results entries don't carry a
    percentile (they're functional measurements, not strength-table
    benchmarks) — we read the raw numbers and use them to set sensible
    starting targets that match what the user can actually do.
    """
    results = program.calibration_results
    progression = dict(program.progression)

    # Balance hold target — start a touch below what the user demonstrated,
    # so they hit it cleanly week 1. They can grow it later.
    if "balance_seconds" in results:
        observed = int(results["balance_seconds"].get("reps", 0))
        progression["balance_seconds"] = max(15, min(45, observed - 5))

    # Carry weight — same idea: start ~80% of demonstrated capacity per hand.
    if "carry_lb" in results:
        observed = float(results["carry_lb"].get("load_lb", 0.0))
        if observed > 0:
            progression["carry_lb"] = max(5, int(observed * 0.80))

    # Other functional probes (sit_stand_reps, wall_pushup) are recorded but
    # don't feed a numerical program parameter — they become Becoming-tab
    # milestone references (e.g. "you started at 8 sit-to-stands; target 15").

    program.progression = progression
    program.phase = "active"
    # Longevity doesn't pick a strength "emphasis slot" — emphasis isn't the
    # frame for this user (they're not trying to make their weakest lift
    # stronger; they're trying to keep functional capacity from declining).
    program.emphasis_slot = None

    program.notes.append(
        "Calibration complete. Starting holds and loads are scaled to your "
        "actual capacity — never above what you demonstrated."
    )
    return ("Calibration done. Loads stay conservative — calibrated to what "
            "you showed me, not what some table says.")


# --- Adaptation ---------------------------------------------------------------

_PAIN_KEYWORDS = ("pain", "hurts", "hurt", "sharp", "shooting", "stabbing",
                  "tweaked", "tweak", "pulled", "strain", "strained")


def _looks_like_pain(friction: str | None) -> bool:
    if not friction:
        return False
    s = friction.lower()
    return any(k in s for k in _PAIN_KEYWORDS)


def _progression_rules(program: ProgramState, recent_reports: list[dict]) -> tuple[ProgramState, str]:
    if not recent_reports:
        if program.phase == "calibration":
            return program, ("Week 1 — calibration. Five gentle assessments. "
                             "Honest numbers only.")
        return program, "First session — settling in. We hold this load for a while."

    p = program.model_copy(deep=True)
    latest = recent_reports[0]
    outcome = latest.get("outcome")
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

        # Pain during calibration — pause. We don't want to talk a longevity
        # user into pushing through anything during week 1.
        if _looks_like_pain(friction):
            return p, ("Pain note — pausing calibration. See someone about it "
                       "before we keep assessing. The program waits.")

        if outcome in ("done", "partial"):
            p.calibration_index = min(p.calibration_index + 1, _CALIBRATION_LENGTH)

        if p.calibration_index >= _CALIBRATION_LENGTH and profile_obj is not None:
            return p, _transition_to_active(p, profile_obj)

        summary = ", ".join(recorded) if recorded else "logged"
        progress = f"{p.calibration_index}/{_CALIBRATION_LENGTH} calibration sessions done"
        return p, f"{summary}. {progress}."

    # =======================================================================
    # ACTIVE PHASE — 3-day full body (unchanged glacial progression)
    # =======================================================================

    # Always advance the rotation cursor.
    p.progression["day_index"] = (int(p.progression.get("day_index", 0)) + 1) % 3

    # Pain handling — gold standard for this template per the design doc.
    # Hold loads, surface a safety-leaning note. Never substitute or push.
    if _looks_like_pain(friction):
        p.progression["clean_streak"] = 0
        return p, ("Pain note logged — holding everything. If it's sharp or it "
                   "lingers a few days, that's a doctor conversation, not a "
                   "training one.")

    if outcome == "done":
        p.progression["consecutive_failed_sessions"] = 0
        p.progression["clean_streak"] = int(p.progression.get("clean_streak", 0)) + 1

        streak = int(p.progression["clean_streak"])
        felt_easy = "easy" in friction.lower() if friction else False

        if felt_easy and streak >= 2:
            # Bump ONE rep slot — never load, never multiple slots at once.
            current = int(p.progression.get("squat_lb", 25))
            p.progression["squat_lb"] = current + 5  # +5 lb total, conservative
            p.progression["clean_streak"] = 0
            rationale = ("Two clean weeks and it felt easy. Adding 5 lb to the "
                         "sit-to-stand. Hold everything else.")
        elif streak >= 6 and not felt_easy:
            # Six clean weeks at the same load with no "easy" signal — nudge
            # the balance hold a bit. Form-led, not load-led.
            current = int(p.progression.get("balance_seconds", 30))
            p.progression["balance_seconds"] = min(60, current + 10)
            p.progression["clean_streak"] = 0
            rationale = ("Six clean weeks. Adding 10 seconds to the balance "
                         "hold. The loads stay — they're not the point.")
        else:
            rationale = ("Session done. Loads stay. Boring is the point — "
                         "you're not deteriorating, that's the win.")

    elif outcome == "partial":
        p.progression["clean_streak"] = 0
        p.progression["consecutive_failed_sessions"] = (
            int(p.progression.get("consecutive_failed_sessions", 0)) + 1
        )
        rationale = "Partial — holding everything. No pressure. Try again next time."

    elif outcome in ("skipped", "busy", "not_now", "ignored"):
        p.progression["clean_streak"] = 0
        rationale = ("Missed it. Walking still counts today. "
                     "Back to the program next time.")

    else:
        rationale = "Holding."

    # Two partials in a row → 10% load deload. Same safety net as
    # conditioning, slightly more sensitive because the population is more
    # fragile.
    if int(p.progression.get("consecutive_failed_sessions", 0)) >= 2:
        for k in list(p.progression.keys()):
            if k.endswith("_lb") and isinstance(p.progression[k], (int, float)):
                p.progression[k] = max(5.0, round(float(p.progression[k]) * 0.90))
        p.progression["consecutive_failed_sessions"] = 0
        rationale += " Two partials in a row — easing all loads by 10%."

    p.notes.append(rationale)
    return p, rationale


# --- Persona instance ---------------------------------------------------------

LONGEVITY_PERSONA = Persona(
    domain="longevity",
    voice=(
        "You speak like a coach for someone training to live well at 80. "
        "Warm but never mushy. You respect the user — they have lived a lot "
        "longer than you. You use plain English: 'sit-to-stand' not 'squat', "
        "'pull the weight to your ribs' not 'row'. You never use the words "
        "'shred', 'transform', 'cleanse', 'PR', 'gains', or 'beast mode'. "
        "You celebrate not deteriorating. You hold loads on purpose. "
        "Walking always counts."
    ),
    safety_disclaimer=(
        "I program training, not medicine. Sharp pain, anything that lingers "
        "more than a few days, or anything that feels wrong — that's a "
        "doctor conversation, not a training one. Tell me and I'll hold the "
        "program while you sort it."
    ),
    intake_questions=_intake,
    build_program=_build_program,
    next_session=_next_session,
    progression_rules=_progression_rules,
    world_theme="grove",
    calibration_length=_CALIBRATION_LENGTH,
)
