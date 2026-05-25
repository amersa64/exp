"""
Exercise catalog tests — lock the contract that drives prescription quality.

These tests don't check the JSON dataset itself (it's vendored read-only).
They check the catalog's *queries* — the surface the persona depends on.
If pick_for_slot stops respecting equipment, the persona will silently
prescribe barbell work to bodyweight users; that bug needs to land here.
"""

from __future__ import annotations

from coach.exercises import (
    ExerciseCatalog,
    catalog,
    normalize_equipment_profile,
)


def test_catalog_loads_known_canonical_lifts():
    c = catalog()
    # The five movement patterns the fitness persona's slot ladders depend on
    # MUST resolve to a real catalog entry. If anyone renames these in the
    # dataset, this test fails loudly instead of silently breaking sessions.
    for name in [
        "Barbell Squat",
        "Goblet Squat",
        "Bodyweight Squat",
        "Barbell Bench Press - Medium Grip",
        "Pushups",
        "Bent Over Barbell Row",
        "Inverted Row",
        "Barbell Deadlift",
        "Standing Military Press",
    ]:
        assert c.get(name) is not None, f"missing canonical lift: {name}"


def test_equipment_profile_normalization():
    # Free-text answers → one of the known profile keys. These are the
    # answers a real user actually writes; if the mapping silently changes
    # they'll start getting wrong prescriptions.
    cases = {
        "full gym": "full_gym",
        "the local gym": "full_gym",
        "barbell+rack at home": "barbell",
        "I have a rack and a bar in the garage": "barbell",
        "dumbbells only": "dumbbell",
        "kettlebells in the basement": "kettlebells",
        "bodyweight only": "bodyweight",
        "no equipment": "bodyweight",
        "": "barbell",  # conservative default — never silently downgrade
    }
    for raw, expected in cases.items():
        assert normalize_equipment_profile(raw) == expected, (
            f"{raw!r} -> {normalize_equipment_profile(raw)}, expected {expected}"
        )


def test_pick_for_slot_respects_equipment():
    c = catalog()
    # Bodyweight-only user must get Bodyweight Squat, NOT Barbell Squat.
    bodyweight = c.equipment_for_profile("bodyweight only")
    ladder = ["Barbell Squat", "Goblet Squat", "Dumbbell Squat", "Bodyweight Squat"]
    assert c.pick_for_slot(ladder, bodyweight).name == "Bodyweight Squat"

    # Dumbbell-only user must get Dumbbell Squat (not barbell, not bodyweight).
    db = c.equipment_for_profile("dumbbells only")
    assert c.pick_for_slot(ladder, db).name == "Dumbbell Squat"

    # Barbell user gets the heaviest variant in the ladder.
    bb = c.equipment_for_profile("barbell+rack at home")
    assert c.pick_for_slot(ladder, bb).name == "Barbell Squat"


def test_pick_for_slot_always_returns_something():
    """The coach owes the user *something* prescribable — never raises."""
    c = catalog()
    # A weird equipment set the ladder doesn't fit cleanly:
    weird = {"foam roll"}  # nothing in the squat ladder uses foam rolls
    ladder = ["Barbell Squat", "Goblet Squat", "Bodyweight Squat"]
    pick = c.pick_for_slot(ladder, weird)
    # Falls back to the last named entry in the ladder rather than crashing.
    assert pick.name == "Bodyweight Squat"


def test_find_filters_compose():
    c = catalog()
    beginner_quad_compounds = c.find(
        primary_muscle="quadriceps",
        level="beginner",
        mechanic="compound",
        category="strength",
    )
    # Should be non-empty and every entry must satisfy ALL filters.
    assert beginner_quad_compounds
    for e in beginner_quad_compounds:
        assert e.level == "beginner"
        assert e.mechanic == "compound"
        assert "quadriceps" in e.primary_muscles
        assert e.category == "strength"
