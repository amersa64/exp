"""
Adaptive coach — interpret the user's free-form feedback into program changes.

This is the "real coach who listens and remembers" layer. The user can push
back on their program in plain English at any time:

  - Exercise-level: "barbell squat kills my left knee, give me something I can
    actually do" → we recommend a real alternative from the catalog AND record
    a standing constraint so the squat never silently comes back.

  - Program-level: "I'm completely wiped after these sessions, it's too much"
    → we interpret the complaint into a concrete directive (cut volume, drop a
    day, lighter loads) and a coach-voice reply, then regenerate the program
    carrying every standing constraint forward.

Both paths produce a ProgramAdjustment (coach memory). The constraint text
each produces is written to be dropped straight into the next build prompt —
that's how "remember the decision for next time" actually works: the
constraint is part of the prompt the split-planner and exercise-picker see.

Why LLM here and not a rules engine: the signal is *language*. "Too much" can
mean volume, frequency, or intensity; "this hurts" can mean swap-the-movement
or reduce-the-load. A coach disambiguates from how it's phrased and what they
know about the person. That's exactly the job an LLM is good at — and the
structured-output schema keeps the result safe to act on.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel

from .exercises import Exercise, ExerciseCatalog
from .llm import LLMClient
from .models import ProgramAdjustment, UserProfile


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exercise-level swap.
# ---------------------------------------------------------------------------


class SwapResult(BaseModel):
    """What the swap interpreter returns to the caller."""
    replacement: str | None       # catalog name chosen, or None if no good fit
    alternatives: list[str]       # other viable options the UI can show
    constraint: str               # build-prompt-ready standing instruction
    coach_response: str           # coach-voice reply to show the user


def _swap_schema(candidate_names: list[str]) -> dict[str, Any]:
    # replacement is enum-bound to the candidate list (+ a sentinel for "none
    # of these fit") so the model literally cannot invent an exercise.
    enum_with_none = candidate_names + ["__none__"]
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["replacement", "alternatives", "constraint", "coach_response"],
        "properties": {
            "replacement": {"type": "string", "enum": enum_with_none},
            "alternatives": {
                "type": "array",
                "items": {"type": "string", "enum": candidate_names},
                "maxItems": 3,
            },
            "constraint": {"type": "string"},
            "coach_response": {"type": "string"},
        },
    }


_SWAP_SYSTEM = """\
You are a strength coach responding to a client who wants to swap an exercise.

They've told you, in their own words, why the current exercise isn't working
and what they want instead. You're given:
  - the exercise they're reacting to
  - their free-form note
  - their profile (level, injuries, equipment, goal)
  - a CANDIDATES list of catalog exercises that hit the same muscles and fit
    their equipment

Your job:
  1. Pick the single best `replacement` from CANDIDATES given their note. If
     NOTHING in the list genuinely addresses their concern, set replacement to
     "__none__" (don't force a bad swap).
  2. List up to 3 `alternatives` from CANDIDATES (excluding the replacement) —
     other reasonable options the client could choose instead.
  3. Write a `constraint`: ONE instruction, written for a future program
     planner, capturing what to avoid and prefer going forward. Be specific
     about the WHY so the planner generalizes correctly. Example:
     "Avoid Barbell Back Squat and other heavily knee-loaded barbell squats —
     client reports left knee pain under load; prefer goblet/box/leg-press
     variants that limit deep knee flexion."
  4. Write a `coach_response`: short, warm, concrete. Acknowledge their note,
     name the swap, one sentence on why it's a good fit. No platitudes, no
     "journey", no emojis.

Honor injuries above all. If their note hints at pain, prefer the gentlest
viable option, not the most similar one.
"""


def interpret_exercise_swap(
    user_id: str,
    exercise: Exercise,
    note: str,
    candidates: list[Exercise],
    profile: UserProfile,
    llm: LLMClient,
) -> tuple[SwapResult, ProgramAdjustment]:
    """LLM reads the note + candidates, recommends a swap, records the memory."""
    candidate_names = [c.name for c in candidates]
    if not candidate_names:
        # No viable alternatives at all — still record the avoid so the
        # exercise stops appearing, and tell the user honestly.
        result = SwapResult(
            replacement=None,
            alternatives=[],
            constraint=f"Avoid {exercise.name} — user requested removal. Note: {note[:160]}",
            coach_response=(
                f"Heard. I'll stop programming {exercise.name}. I don't have a "
                "clean equipment-matched alternative right now, so I'll rebalance "
                "the rest of the session around it."
            ),
        )
        return result, _to_adjustment(user_id, "exercise", note, exercise.name, None, result)

    schema = _swap_schema(candidate_names)
    user_msg = (
        f"EXERCISE THEY WANT TO SWAP: {exercise.name}\n"
        f"  primary_muscles: {exercise.primary_muscles}\n"
        f"  equipment: {exercise.equipment}\n\n"
        f"THEIR NOTE: {note}\n\n"
        f"PROFILE:\n{json.dumps(_profile_slice(profile), indent=2)}\n\n"
        f"CANDIDATES (replacement/alternatives MUST come from here):\n"
        + "\n".join(f"  - {n}" for n in candidate_names)
    )
    raw = llm.complete_with_schema(
        _SWAP_SYSTEM, user_msg, schema, max_tokens=600, task="EXERCISE_PICKER",
    )
    replacement = raw.get("replacement")
    if replacement == "__none__":
        replacement = None
    result = SwapResult(
        replacement=replacement,
        alternatives=[a for a in raw.get("alternatives", []) if a != replacement][:3],
        constraint=raw.get("constraint", f"Avoid {exercise.name}. Note: {note[:160]}"),
        coach_response=raw.get("coach_response", "Got it — I've updated your program."),
    )
    adj = _to_adjustment(user_id, "exercise", note, exercise.name, replacement, result)
    return result, adj


def direct_exercise_swap(
    user_id: str,
    exercise: Exercise,
    chosen: str,
    note: str | None = None,
) -> tuple[SwapResult, ProgramAdjustment]:
    """Swap to an explicitly-chosen replacement — no LLM.

    Used when the user picks from the default equipment-matched alternates the
    UI already showed them. We know the replacement, so there's nothing to
    reason about: record the standing constraint (so the coach remembers the
    swap and the original doesn't silently return) and patch the program. This
    keeps the "coach remembers" semantics identical to the note path without
    spending a model call on a decision the user already made.
    """
    user_note = note or f"Quick swap to {chosen}"
    constraint = (
        f"Avoid {exercise.name} — user swapped it for {chosen}. "
        f"Prefer {chosen} (or an equivalent that hits the same muscles) for "
        "this slot going forward."
    )
    coach_response = (
        f"Done — {chosen} in place of {exercise.name} from here on. I'll remember that."
    )
    result = SwapResult(
        replacement=chosen,
        alternatives=[],
        constraint=constraint,
        coach_response=coach_response,
    )
    adj = _to_adjustment(user_id, "exercise", user_note, exercise.name, chosen, result)
    return result, adj


# ---------------------------------------------------------------------------
# Program-level feedback.
# ---------------------------------------------------------------------------


class FeedbackResult(BaseModel):
    """What the program-feedback interpreter returns."""
    # Whether this feedback warrants regenerating the whole program. Small
    # tweaks (e.g. "I prefer mornings") might be remembered without a rebuild.
    regenerate: bool
    constraint: str               # build-prompt-ready standing instruction
    coach_response: str           # coach-voice reply
    change_summary: str           # plain-English "here's what I changed"


def _feedback_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["regenerate", "constraint", "coach_response", "change_summary"],
        "properties": {
            "regenerate": {"type": "boolean"},
            "constraint": {"type": "string"},
            "coach_response": {"type": "string"},
            "change_summary": {"type": "string"},
        },
    }


_FEEDBACK_SYSTEM = """\
You are a strength coach. A client has given you free-form feedback about
their CURRENT program as a whole — not a single exercise. Examples of what
they might say: "I'm exhausted, this is too much", "I can only train 3 days
now", "the sessions run too long", "I want more upper body", "Wednesdays
never work for me".

You're given their note, a summary of their current program, their profile,
and any standing constraints already in effect.

Your job:
  1. Decide `regenerate`: true if the feedback changes the SHAPE of the
     program (volume, frequency, day count, emphasis, session length) and
     warrants rebuilding. false if it's a soft preference you can just
     remember for next time without rebuilding now.
  2. Write a `constraint`: ONE build-prompt-ready instruction capturing the
     change to apply on the next build. Be concrete and quantitative where
     possible. Examples:
     "Reduce per-session volume ~25% (fewer accessory exercises, 3-4 working
      movements per day max) — client reports excessive fatigue."
     "Drop to 3 training days per week — client's schedule changed."
  3. Write a `coach_response`: short, warm, specific. Acknowledge the feedback,
     state what you're changing. No platitudes, no "journey", no emojis.
  4. Write a `change_summary`: one plain sentence describing the concrete
     change, for a "what changed" UI line.

Be conservative about regenerate=true for vague positivity ("going well!") —
that's not a change request. Be decisive about it for fatigue/pain/time
complaints — those are real and need action.
"""


def interpret_program_feedback(
    user_id: str,
    note: str,
    program_summary: str,
    profile: UserProfile,
    prior_constraints: list[str],
    llm: LLMClient,
) -> tuple[FeedbackResult, ProgramAdjustment]:
    """LLM interprets whole-program feedback into a directive + memory."""
    user_msg = (
        f"THEIR FEEDBACK: {note}\n\n"
        f"CURRENT PROGRAM:\n{program_summary}\n\n"
        f"PROFILE:\n{json.dumps(_profile_slice(profile), indent=2)}\n\n"
        f"STANDING CONSTRAINTS ALREADY IN EFFECT:\n"
        + ("\n".join(f"  - {c}" for c in prior_constraints) if prior_constraints else "  (none)")
    )
    raw = llm.complete_with_schema(
        _FEEDBACK_SYSTEM, user_msg, _feedback_schema(), max_tokens=700, task="SPLIT_PLANNER",
    )
    result = FeedbackResult(
        regenerate=bool(raw.get("regenerate", True)),
        constraint=raw.get("constraint", f"User feedback: {note[:160]}"),
        coach_response=raw.get("coach_response", "Heard. I've taken that on board."),
        change_summary=raw.get("change_summary", "Adjusted based on your feedback."),
    )
    adj = ProgramAdjustment(
        user_id=user_id,
        scope="program",
        user_note=note,
        target_exercise=None,
        replacement_exercise=None,
        constraint=result.constraint,
        coach_response=result.coach_response,
    )
    return result, adj


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------


def _to_adjustment(
    user_id: str,
    scope: str,
    note: str,
    target: str | None,
    replacement: str | None,
    result: SwapResult,
) -> ProgramAdjustment:
    return ProgramAdjustment(
        user_id=user_id,
        scope=scope,  # type: ignore[arg-type]
        user_note=note,
        target_exercise=target,
        replacement_exercise=replacement,
        constraint=result.constraint,
        coach_response=result.coach_response,
    )


def _profile_slice(profile: UserProfile) -> dict[str, Any]:
    return {
        "goal_domain": profile.domain,
        "intake_answers": profile.answers,
        "derived_profile": profile.derived,
    }
