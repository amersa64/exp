"""
Persona = a domain specialist (Section 4.2).

The persona is DATA-DRIVEN by design (Rubric G2): adding domain #2 should be
authoring a new Persona instance against this same interface, not editing the
engine. v1 ships exactly one (Fitness), but the seams are real.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..models import (
    AtomicAction,
    Habit,
    Identity,
    Milestone,
    ProgramState,
    Session,
    UserProfile,
)


@dataclass
class IntakeQuestion:
    key: str
    q: str
    # Optional cheap validator/coercer — keeps the LLM-derived profile sane.
    coerce: Callable[[str], object] | None = None


@dataclass
class Persona:
    """A domain specialist definition."""
    domain: str
    voice: str                         # short style guide string used in LLM system prompts
    safety_disclaimer: str

    # --- Coaching lifecycle hooks ---
    # Functions live here so the engine doesn't grow domain-specific branches.
    intake_questions: Callable[[UserProfile | None], list[IntakeQuestion]]
    build_program: Callable[[UserProfile], tuple[ProgramState, list[Milestone], list[Habit]]]
    next_session: Callable[[ProgramState, UserProfile], Session]
    progression_rules: Callable[[ProgramState, list[dict]], tuple[ProgramState, str]]
    # (program, recent_reports) -> (new_program, human-readable rationale)

    # --- World theming ---
    world_theme: str = "default"
