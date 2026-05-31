"""
Persona registry + goal → domain dispatch.

Each goal a user can pick during intake maps to a persona. The dispatcher
reads `profile.answers["goal"]` and returns the right domain.

Goal → domain mapping is the contract between the intake form (iOS) and the
program engine. Don't change the goal string keys without updating both sides.
"""

from .base import IntakeQuestion, Persona
from .strength import STRENGTH_PERSONA
from .hypertrophy import HYPERTROPHY_PERSONA
from .conditioning import CONDITIONING_PERSONA
from .longevity import LONGEVITY_PERSONA
from .discipline import DISCIPLINE_PERSONA


# All personas, keyed by domain. The domain key is the canonical identifier
# stored in the DB on UserProfile.domain.
#
# Note "fitness" is a back-compat alias for users in the DB from v1 (before
# the multi-goal split). It points to the strength persona.
PERSONAS: dict[str, Persona] = {
    STRENGTH_PERSONA.domain:     STRENGTH_PERSONA,
    HYPERTROPHY_PERSONA.domain:  HYPERTROPHY_PERSONA,
    CONDITIONING_PERSONA.domain: CONDITIONING_PERSONA,
    LONGEVITY_PERSONA.domain:    LONGEVITY_PERSONA,
    DISCIPLINE_PERSONA.domain:   DISCIPLINE_PERSONA,
    "fitness":                   STRENGTH_PERSONA,   # v1 alias
}


# Maps the iOS-side goal string to a backend domain (and therefore persona).
# All five goals now have a real template — no fallback paths remain. Adding
# a new goal here without adding a persona will fall through to strength via
# goal_to_domain()'s default, but the UI's FallbackBanner is gone (Trainview
# no longer treats any of the canonical five goals as fallback).
_GOAL_TO_DOMAIN: dict[str, str] = {
    "get_stronger":  "strength",
    "build_muscle":  "hypertrophy",
    "lose_weight":   "conditioning",
    "age_well":      "longevity",
    "discipline":    "discipline",
}


def goal_to_domain(goal: str | None) -> str:
    """
    Map the goal answer to the persona domain.

    Defaults to "strength" for missing/unknown goals — every user gets a
    working program, never an error.
    """
    if not goal:
        return "strength"
    return _GOAL_TO_DOMAIN.get(goal, "strength")


def domain_is_implemented_for_goal(goal: str | None) -> bool:
    """True if we ship a real template for this goal yet (not just the strength fallback)."""
    return goal in _GOAL_TO_DOMAIN
