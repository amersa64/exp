"""
Per-task model configuration.

Each LLM call in this codebase has a task tag (split_planner, exercise_picker,
voice, journal, ...). Defaults live here in code — reviewable, version-
controlled, and overridable per-task via env (COACH_LLM_MODEL_<TASK>) when you
want to run an experiment without editing source.

Why per-task instead of one global model: a reasoning-heavy program plan wants
a stronger model than a one-line nudge reply. Forcing every call onto the same
tier either overpays for nudges or underdelivers for plans.
"""

from __future__ import annotations

import os


# Defaults per task. Keys are uppercase identifiers used as task tags at the
# call site (e.g. llm.complete_json(..., task="SPLIT_PLANNER")).
#
# The string here is the *model name* — provider is resolved separately
# (LLMClient picks the provider from whichever API key is present, and the
# model name needs to be valid for that provider).
_DEFAULTS: dict[str, str] = {
    # Reasoning-heavy: picks weekly split from rich profile. Runs ~1x per
    # program. Big model justified.
    "SPLIT_PLANNER":   "gpt-4o",

    # Constrained-choice: picks exercises from a small candidate enum per day.
    # Runs once per session in the split (3-6x per program). Mini is fine for
    # the constrained-choice shape; bump to gpt-4o if quality lags.
    "EXERCISE_PICKER": "gpt-4o",

    # Short prose, high volume, cost-sensitive. Stays on mini.
    "NUDGE":           "gpt-4o-mini",
    "VOICE":           "gpt-4o-mini",
    "JOURNAL":         "gpt-4o-mini",
    "COACH_RESPONSE":  "gpt-4o-mini",
    "ADAPT":           "gpt-4o-mini",
    "DERIVE_PROFILE":  "gpt-4o-mini",
}


def model_for(task: str | None) -> str | None:
    """Resolve the model name for a task tag.

    Resolution order:
      1) COACH_LLM_MODEL_<TASK> env var (one-off experiment override)
      2) Default registered above
      3) None — caller falls back to provider default
    """
    if not task:
        return None
    key = task.upper()
    override = os.environ.get(f"COACH_LLM_MODEL_{key}")
    if override:
        return override
    return _DEFAULTS.get(key)
