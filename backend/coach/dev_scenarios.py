"""
Dev scenarios — pre-built user states for fast iteration.

Calling POST /dev/seed with a goal + scenario name wipes the user and
applies a canned state, so you can jump straight to "calibration session
3 of 5" or "active phase, 50 votes, 21-day streak" without manually
clicking through onboarding every time.

These are dev-only paths — they bypass mirror integrity on WorldState
and short-circuit the LLM-driven profile derivation. Do not call them
from any production code path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Literal

from .calibration import lifting_calibration_days, record_top_sets
from .models import (
    AtomicAction,
    Habit,
    Identity,
    Milestone,
    ProgramState,
    UserProfile,
    WorldState,
    _now,
)
from .personas import PERSONAS, goal_to_domain


Goal = Literal["get_stronger", "build_muscle", "lose_weight", "age_well", "discipline"]


@dataclass
class Scenario:
    """One named pre-built state."""
    name: str
    label: str
    description: str
    phase: Literal["calibration", "active"]
    # During calibration: how many sessions have been logged (0..5).
    calibration_index: int = 0
    # If True, populate calibration_results with realistic top sets so the
    # active phase transitions cleanly (otherwise active phase has empty
    # results, which works but is less interesting to iterate against).
    seeded_calibration_results: bool = False
    # Active phase only.
    votes: int = 0
    streak_days: int = 0
    # How many days ago the last verified event was. 0 = today (current
    # streak alive); 1 = yesterday (streak still alive); 4 = streak broken.
    days_since_last_verified: int = 0


SCENARIOS: dict[str, Scenario] = {
    "fresh": Scenario(
        name="fresh",
        label="Fresh — just finished intake",
        description="Phase = calibration, index 0/5. The very first session waiting.",
        phase="calibration",
        calibration_index=0,
    ),
    "mid_calibration": Scenario(
        name="mid_calibration",
        label="Mid calibration — 3/5 done",
        description="3 calibration sessions logged with realistic top sets. "
                    "Tests the banner mid-progress and the calibration_results card.",
        phase="calibration",
        calibration_index=3,
        seeded_calibration_results=True,
    ),
    "calibration_done": Scenario(
        name="calibration_done",
        label="Calibration complete — fresh active",
        description="Just transitioned to active phase. Real loads from "
                    "calibration. 0 votes, 0 streak — clean slate to start training.",
        phase="active",
        seeded_calibration_results=True,
    ),
    "active_low": Scenario(
        name="active_low",
        label="Active — early engagement",
        description="3 votes, 1-day streak. Hero sky shows the first few stars; "
                    "flame is a low ember.",
        phase="active",
        seeded_calibration_results=True,
        votes=3,
        streak_days=1,
    ),
    "active_growing": Scenario(
        name="active_growing",
        label="Active — growing (15 votes, 7-day streak)",
        description="Mid-program. Flame is climbing toward full glow; "
                    "constellation is recognizable.",
        phase="active",
        seeded_calibration_results=True,
        votes=15,
        streak_days=7,
    ),
    "active_thriving": Scenario(
        name="active_thriving",
        label="Active — thriving (50 votes, 21-day streak)",
        description="Long-haul rhythm. Flame at full glow, sky dense.",
        phase="active",
        seeded_calibration_results=True,
        votes=50,
        streak_days=21,
    ),
    "active_legendary": Scenario(
        name="active_legendary",
        label="Active — legendary (120 votes, 60-day streak)",
        description="Past the 90-star cap. Tests the brightness-of-existing-"
                    "stars overflow logic.",
        phase="active",
        seeded_calibration_results=True,
        votes=120,
        streak_days=60,
    ),
    "streak_just_broken": Scenario(
        name="streak_just_broken",
        label="Streak broken — sky stays, flame rests",
        description="30 votes accumulated but last verified was 4 days ago. "
                    "Confirms the design intent: missed days don't erase past votes.",
        phase="active",
        seeded_calibration_results=True,
        votes=30,
        streak_days=0,
        days_since_last_verified=4,
    ),
}


# Realistic-looking top sets for a 32-year-old 180-lb male — adjust the
# benchmarks if you want to test the percentile labels at the boundaries.
# Numbers chosen so the resulting active-phase loads are sensible (not
# zero, not crushing).
_DEFAULT_CALIBRATION_TOP_SETS: dict[str, dict[str, float]] = {
    "squat":    {"reps": 5, "load_lb": 225.0},   # est 1RM ~262 → novice
    "bench":    {"reps": 5, "load_lb": 135.0},   # est 1RM ~158 → novice
    "ohp":      {"reps": 5, "load_lb": 75.0},    # est 1RM ~88  → novice (often the weakest)
    "row":      {"reps": 5, "load_lb": 135.0},
    "pullup":   {"reps": 3, "load_lb": 0.0},
    "deadlift": {"reps": 5, "load_lb": 275.0},
}


def _seed_profile_answers(goal: str) -> dict[str, str]:
    """Stock intake answers so the persona's _intake() questions all have a value
    if needed downstream. We keep them consistent across scenarios so the
    only thing that changes between seedings is phase/votes/streak."""
    base = {
        "goal": goal,
        "sex": "male",
        "age": "32",
        "bodyweight_lb": "180",
        "experience": "novice",
        "days_per_week": "3",
        "injuries": "none",
        "equipment": "full gym",
        "anchor_habit": "morning coffee",
        "training_location": "home gym",
    }
    # Persona-specific extras so derive_profile sees a complete set.
    if goal == "discipline":
        base["prior_disordered"] = "no"
        base["outdoor_access"] = "yes"
    if goal == "age_well":
        base["mobility_limits"] = "none"
    return base


def apply_scenario(store, user_id: str, goal: Goal, scenario_name: str,
                    identity_statement: str = "I am someone who shows up.") -> dict:
    """
    Wipe the user and seed the named scenario. Returns a small summary dict
    describing what was applied — surfaced back to iOS so the UI can show
    "Applied: active_growing → 15 votes, 7-day streak".
    """
    if scenario_name not in SCENARIOS:
        raise ValueError(f"unknown scenario: {scenario_name}")
    scenario = SCENARIOS[scenario_name]

    domain = goal_to_domain(goal)
    persona = PERSONAS[domain]

    store.wipe_user(user_id)

    # --- profile (bypass the LLM derive step; just set answers + derived).
    answers = _seed_profile_answers(goal)
    profile = UserProfile(
        user_id=user_id,
        domain=domain,
        answers=answers,
        # Mirror the answers as derived so persona code that reads
        # profile.derived sees consistent values.
        derived={k: v for k, v in answers.items()},
    )
    store.save_profile(profile)

    # --- program (run the persona's build_program, then mutate for scenario)
    program, milestones, habits = persona.build_program(profile)
    identity = Identity(
        user_id=user_id,
        statement=identity_statement,
        domain=domain,
        anchor_habit=answers.get("anchor_habit"),
    )
    store.save_identity(identity)
    for m in milestones:
        m.parent_identity_id = identity.id
        store.save_milestone(m)
    for h in habits:
        if not any(m.id == h.parent_milestone_id for m in milestones):
            h.parent_milestone_id = milestones[0].id
        store.save_habit(h)

    # Seed calibration_results if the scenario calls for it. This is what
    # makes the transition to active phase realistic — without these the
    # active program falls back to defaults.
    if scenario.seeded_calibration_results:
        # The longevity persona uses functional probes that aren't in the
        # default lifting set — for longevity, we seed those instead.
        if goal == "age_well":
            longevity_results = {
                "sit_stand_reps":   {"reps": 18, "load_lb": 0.0},
                "wall_pushup":      {"reps": 12, "load_lb": 0.0},
                "balance_seconds":  {"reps": 22, "load_lb": 0.0},
                "carry_lb":         {"reps": 1,  "load_lb": 15.0},
            }
            record_top_sets(program, profile, longevity_results)
        else:
            record_top_sets(program, profile, _DEFAULT_CALIBRATION_TOP_SETS)

    # Apply phase transition if scenario lands in active phase.
    if scenario.phase == "active":
        # Drive the persona's own transition helper if the program is still in
        # calibration. Each persona exposes _transition_to_active via its
        # module — we import lazily to avoid circular imports.
        if program.phase == "calibration":
            transition = _persona_transition(domain)
            if transition is not None:
                transition(program, profile)
            else:
                # Fallback: flip the flag and trust the persona's _next_session
                # to handle minimal progression. Only useful if a future
                # persona doesn't expose a transition helper.
                program.phase = "active"
    else:
        # Calibration phase — set the index per scenario.
        program.calibration_index = scenario.calibration_index

    store.save_program(program)

    # --- world (votes + streak + last_verified_day)
    world = WorldState(
        user_id=user_id,
        theme=persona.world_theme,
        currency=scenario.votes * 7,  # rough — matches grow()'s vote/currency ratio
        streak_days=scenario.streak_days,
        longest_streak=max(scenario.streak_days, scenario.votes // 3),
        identity_votes=scenario.votes,
    )
    if scenario.votes > 0:
        last = (_now() - timedelta(days=scenario.days_since_last_verified)).date().isoformat()
        world.last_verified_day = last
    store.dev_force_save_world(world)

    return {
        "applied": scenario.name,
        "label": scenario.label,
        "goal": goal,
        "phase": program.phase,
        "calibration_index": program.calibration_index,
        "votes": scenario.votes,
        "streak_days": scenario.streak_days,
        "days_since_last_verified": scenario.days_since_last_verified,
        "emphasis_slot": program.emphasis_slot,
    }


def _persona_transition(domain: str):
    """Return the persona's `_transition_to_active` callable, or None."""
    if domain == "strength":
        from .personas.strength import _transition_to_active
        return _transition_to_active
    if domain == "hypertrophy":
        from .personas.hypertrophy import _transition_to_active
        return _transition_to_active
    if domain == "conditioning":
        from .personas.conditioning import _transition_to_active
        return _transition_to_active
    if domain == "longevity":
        from .personas.longevity import _transition_to_active
        return _transition_to_active
    if domain == "discipline":
        from .personas.discipline import _transition_to_active
        return _transition_to_active
    return None


def scenarios_list() -> list[dict]:
    """Surface available scenarios so iOS can render them as a picker."""
    return [
        {
            "name": s.name,
            "label": s.label,
            "description": s.description,
            "phase": s.phase,
            "votes": s.votes,
            "streak_days": s.streak_days,
        }
        for s in SCENARIOS.values()
    ]


GOALS_LIST: list[dict[str, str]] = [
    {"value": "get_stronger", "label": "Get stronger"},
    {"value": "build_muscle", "label": "Build muscle"},
    {"value": "lose_weight",  "label": "Lose weight"},
    {"value": "age_well",     "label": "Age well"},
    {"value": "discipline",   "label": "Discipline (75 Hard)"},
]
