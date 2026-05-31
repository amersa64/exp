"""
Tests for the adaptive-coach constraint machinery.

These cover the DETERMINISTIC half of the feature — adjustment persistence,
avoided-exercise filtering, and validation rejection. The LLM interpretation
(adjust.interpret_*) runs in stub mode here; we test that the plumbing around
it enforces the user's vetoes, which is the safety-critical part. A swap the
user asked for must NEVER silently come back.
"""

from __future__ import annotations

from coach.ai_program import (
    DayPlan,
    DaySpec,
    ExercisePick,
    _filter_candidates,
    validate_plan,
)
from coach.exercises import catalog
from coach.models import AdjustmentLog, ProgramAdjustment
from coach.store import Store


def _adj(user_id: str, target: str, replacement: str | None = None) -> ProgramAdjustment:
    return ProgramAdjustment(
        user_id=user_id,
        scope="exercise",
        user_note="it hurts",
        target_exercise=target,
        replacement_exercise=replacement,
        constraint=f"Avoid {target}",
        coach_response="Swapped.",
    )


def test_adjustment_log_roundtrips_through_store():
    store = Store(":memory:")
    log = store.get_adjustments("u1")
    assert log.adjustments == []  # empty log for a new user, not None

    log.append(_adj("u1", "Barbell Squat", "Goblet Squat"))
    store.save_adjustments(log)

    reloaded = store.get_adjustments("u1")
    assert len(reloaded.adjustments) == 1
    assert reloaded.avoided_exercises() == {"barbell squat"}
    assert len(reloaded.active_constraints()) == 1


def test_inactive_constraints_are_excluded():
    log = AdjustmentLog(user_id="u1")
    a = _adj("u1", "Barbell Squat")
    a.active = False
    log.append(a)
    assert log.avoided_exercises() == set()
    assert log.active_constraints() == []


def test_filter_candidates_drops_avoided_exercise():
    cat = catalog()
    spec = DaySpec(
        day_index=1, kind="training", name="Legs",
        primary_muscles=["quadriceps"], secondary_muscles=[],
        target_minutes=45, pattern_focus="squat",
    )
    equip = cat.equipment_for_profile("full gym")

    without = _filter_candidates(spec, cat, equip, level=None)
    names_without = {e.name for e in without}
    # Pick a real quad exercise that shows up, then ensure avoiding it removes it.
    assert names_without, "expected some quad candidates"
    victim = next(iter(names_without))

    with_avoid = _filter_candidates(
        spec, cat, equip, level=None, avoided={victim.lower()},
    )
    assert victim not in {e.name for e in with_avoid}


def test_validate_plan_rejects_avoided_pick():
    cat = catalog()
    spec = DaySpec(
        day_index=1, kind="training", name="Legs",
        primary_muscles=["quadriceps"], secondary_muscles=[],
        target_minutes=45, pattern_focus="squat",
    )
    # Force an avoided exercise into the picks and confirm validation strips it.
    plan = DayPlan(spec=spec, exercises=[
        ExercisePick(catalog_name="Barbell Squat", slot="primary_compound", rationale="x"),
    ])
    equip = cat.equipment_for_profile("full gym")
    cleaned, issues = validate_plan(plan, cat, equip, avoided={"barbell squat"})
    assert cleaned.exercises == []
    assert any(i.issue == "avoided_by_user" for i in issues)
