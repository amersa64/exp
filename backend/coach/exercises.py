"""
Exercise catalog — single source of truth for prescribable lifts.

Backed by `backend/data/exercises.json` (vendored from yuhonas/free-exercise-db,
MIT license, ~870 exercises). Loaded once at import time and indexed for fast
lookup by name / equipment / level / muscle.

Why this exists: a coach is not a tracker. A tracker knows about three lifts.
A coach knows about hundreds, picks the right one for the user's equipment
and ability, and substitutes intelligently when the user reports trouble.
The persona uses this catalog to do exactly that — and the LLM nudge author
gets real cue text ("keep your chest up at the bottom") instead of placeholder
copy.

We never write to this file at runtime — it's frozen reference data, vendored
so the system runs offline (Section 8 — no required external services).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

from pydantic import BaseModel, Field


# Resolve the vendored JSON relative to this module so the server works from
# any CWD. backend/coach/exercises.py → backend/data/exercises.json.
_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "exercises.json"


class Exercise(BaseModel):
    """One entry from the free-exercise-db dataset."""
    name: str
    force: Optional[str] = None              # push / pull / static
    level: Optional[str] = None              # beginner / intermediate / expert
    mechanic: Optional[str] = None           # compound / isolation
    equipment: Optional[str] = None          # barbell / dumbbell / body only / ...
    primary_muscles: list[str] = Field(default_factory=list, alias="primaryMuscles")
    secondary_muscles: list[str] = Field(default_factory=list, alias="secondaryMuscles")
    instructions: list[str] = Field(default_factory=list)
    category: Optional[str] = None
    images: list[str] = Field(default_factory=list)
    id: Optional[str] = None

    model_config = {"populate_by_name": True}

    def first_instruction(self) -> str | None:
        """The single most useful cue string for the nudge author to lean on."""
        return self.instructions[0] if self.instructions else None


# Map free-text intake answers ("barbell+rack at home") to a set of equipment
# values the user can actually use. Equipment=None in the dataset is largely
# stretches/warmups — safe to treat as bodyweight so they're always available.
_EQUIPMENT_PROFILES: dict[str, set[str | None]] = {
    "full_gym":    {"barbell", "dumbbell", "body only", "cable", "machine",
                    "kettlebells", "bands", "medicine ball", "exercise ball",
                    "foam roll", "e-z curl bar", "other", None},
    "barbell":     {"barbell", "body only", "e-z curl bar", "other", None},
    "dumbbell":    {"dumbbell", "body only", "other", None},
    "bodyweight":  {"body only", None},
    "kettlebells": {"kettlebells", "body only", None},
}


def normalize_equipment_profile(raw: str | None) -> str:
    """Map a free-text intake answer to one of the EQUIPMENT_PROFILES keys.

    Conservative defaults: when in doubt, assume barbell+rack (the canonical
    novice strength setup). Never default to bodyweight — that would silently
    narrow the prescription for users who didn't bother describing their gym.
    """
    s = (raw or "").lower()
    if "full gym" in s or "commercial" in s: return "full_gym"
    if ("gym" in s) and ("home" not in s): return "full_gym"
    if "barbell" in s or "rack" in s: return "barbell"
    if "kettle" in s: return "kettlebells"
    if "dumbbell" in s: return "dumbbell"
    if "bodyweight" in s or "body only" in s or "no equipment" in s: return "bodyweight"
    return "barbell"


class ExerciseCatalog:
    """In-memory index of the vendored exercise dataset."""

    def __init__(self, exercises: list[Exercise]) -> None:
        self.exercises = exercises
        self._by_lower_name = {e.name.lower(): e for e in exercises}

    @classmethod
    def load(cls, path: Path | None = None) -> "ExerciseCatalog":
        data = json.loads((path or _DATA_PATH).read_text())
        return cls([Exercise.model_validate(d) for d in data])

    # -- query primitives ----------------------------------------------------

    def find(
        self,
        *,
        name_contains: str | None = None,
        equipment: Iterable[str | None] | None = None,
        level: str | None = None,
        primary_muscle: str | None = None,
        category: str | None = None,
        mechanic: str | None = None,
    ) -> list[Exercise]:
        """Filter the catalog. All criteria AND together; omitted = no filter."""
        eq = set(equipment) if equipment is not None else None
        nc = (name_contains or "").lower() or None
        pm = (primary_muscle or "").lower() or None
        out: list[Exercise] = []
        for e in self.exercises:
            if nc and nc not in e.name.lower():
                continue
            if eq is not None and e.equipment not in eq:
                continue
            if level and e.level != level:
                continue
            if pm and not any(pm == m.lower() for m in e.primary_muscles):
                continue
            if category and e.category != category:
                continue
            if mechanic and e.mechanic != mechanic:
                continue
            out.append(e)
        return out

    def get(self, name: str) -> Exercise | None:
        """Exact case-insensitive name lookup; None if not found."""
        return self._by_lower_name.get(name.lower())

    # -- coaching helpers ----------------------------------------------------

    def equipment_for_profile(self, raw_answer: str | None) -> set[str | None]:
        """Set of catalog equipment values the user actually has."""
        return _EQUIPMENT_PROFILES[normalize_equipment_profile(raw_answer)]

    def pick_for_slot(
        self,
        candidates: list[str],
        available_equipment: set[str | None],
    ) -> Exercise:
        """
        Walk an ordered list of preferred exercise names and return the first
        one the user has equipment for. Last entry in the list MUST be
        unconditionally available (typically a bodyweight movement) — we
        return it as a hard fallback rather than raise, because the coach
        always owes the user *something* to do.
        """
        for name in candidates:
            ex = self.get(name)
            if ex is None:
                continue
            if ex.equipment in available_equipment:
                return ex
        # Hard fallback: last named exercise, equipment be damned.
        # Better to prescribe the wrong thing than to crash a session.
        for name in reversed(candidates):
            ex = self.get(name)
            if ex is not None:
                return ex
        raise ValueError(f"No catalog entry matched any of: {candidates}")

    def regression_for(
        self,
        exercise: Exercise,
        available_equipment: set[str | None],
    ) -> Exercise:
        """
        Find an easier variant of `exercise` the user can do — used when the
        user reports trouble ('knee hurts', repeated partial). Heuristic:
        same primary muscle, beginner level, preferring body-only over
        loaded variants. Falls back to the input if no simpler option fits.
        """
        if not exercise.primary_muscles:
            return exercise
        primary = exercise.primary_muscles[0]
        for eq_pref in [{"body only", None}, {"dumbbell"}, available_equipment]:
            eq_set = eq_pref & available_equipment
            if not eq_set:
                continue
            for c in self.find(
                primary_muscle=primary,
                level="beginner",
                equipment=eq_set,
                category="strength",
                mechanic="compound",
            ):
                if c.name != exercise.name:
                    return c
        return exercise


# Module-level singleton — load once per process. lru_cache makes this both
# lazy and idempotent; tests can call catalog.cache_clear() to force a reload.
@lru_cache(maxsize=1)
def catalog() -> ExerciseCatalog:
    return ExerciseCatalog.load()
