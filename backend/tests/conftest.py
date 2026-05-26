"""
Shared test fixtures.

The big one: scrub LLM credentials from the environment for the entire test
session. Tests must always run in stub mode — deterministic, free, instant.
If `.env` happens to contain a real API key (it usually does on a dev box
once the app is wired up), pytest would otherwise hit the live model and
the suite slows from <1s to multiple minutes AND starts depending on
provider behavior we don't control.

The single autouse fixture below removes the keys BEFORE any test code or
LLMClient is constructed, so the provider-selection path lands on stub.
Individual tests that need to exercise provider routing (see
test_llm_provider.py) set the env vars back inside their own fixtures
via the standard monkeypatch fixture; those changes are local to that
test and roll back at teardown, so the global stub default is restored.
"""

from __future__ import annotations

import os

import pytest


_LLM_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "COACH_LLM_PROVIDER",
    "COACH_LLM_MODEL",
)


@pytest.fixture(autouse=True)
def _scrub_llm_env(monkeypatch):
    """Force stub mode for every test unless a test opts back in."""
    for var in _LLM_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    yield
