"""
LLM provider-selection tests.

These don't exercise the real APIs — they verify the *routing* logic:
which provider gets picked given a particular env, what happens when
the chosen key is missing, and that the stub path stays usable when
neither key is set. Provider-specific request shape is delegated to
the SDKs themselves; we trust those, we don't re-test them.
"""

from __future__ import annotations

import json

import pytest

from coach import llm as llm_mod
from coach.llm import LLMClient


@pytest.fixture
def clean_env(monkeypatch):
    """Strip provider knobs so each test starts from a known-empty state."""
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY",
              "COACH_LLM_PROVIDER", "COACH_LLM_MODEL"):
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


def test_no_key_falls_through_to_stub(clean_env):
    c = LLMClient()
    assert c.provider_name == "stub"
    assert c._client is None
    assert c.model == "stub"
    # Stub still answers — that's the offline contract.
    resp = c.complete("plain system", "plain user", max_tokens=50)
    assert resp.used_stub is True
    assert resp.text  # non-empty fallback


def test_explicit_provider_without_key_stays_stub(clean_env):
    """Setting the env var to 'openai' with no key must NOT crash startup —
    we degrade to stub and the system keeps running. Otherwise a typo'd
    key kills the backend for everyone."""
    clean_env.setenv("COACH_LLM_PROVIDER", "openai")
    c = LLMClient()
    assert c.provider_name == "stub"


def test_anthropic_key_selects_anthropic(clean_env, monkeypatch):
    """When only ANTHROPIC_API_KEY is set the client routes to Anthropic.

    We patch _safe_init to skip real SDK construction (which would try to
    actually authenticate). The point of this test is the *selection
    decision*, not the SDK round-trip.
    """
    clean_env.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")

    class _Fake:
        name = "anthropic"
        model = "claude-fake"
        def complete(self, system, user, max_tokens, *, json_mode, model=None, json_schema=None): return "ok"

    monkeypatch.setattr(llm_mod, "_safe_init", lambda cls, model: _Fake())
    c = LLMClient()
    assert c.provider_name == "anthropic"
    assert c.complete("s", "u").text == "ok"


def test_openai_key_selects_openai(clean_env, monkeypatch):
    clean_env.setenv("OPENAI_API_KEY", "sk-fake")

    class _Fake:
        name = "openai"
        model = "gpt-fake"
        def complete(self, system, user, max_tokens, *, json_mode, model=None, json_schema=None): return "ok"

    monkeypatch.setattr(llm_mod, "_safe_init", lambda cls, model: _Fake())
    c = LLMClient()
    assert c.provider_name == "openai"


def test_both_keys_anthropic_wins(clean_env, monkeypatch):
    """Tie-break documented in the docstring: Anthropic wins when both
    keys are present and no explicit COACH_LLM_PROVIDER is set."""
    clean_env.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
    clean_env.setenv("OPENAI_API_KEY", "sk-fake")
    monkeypatch.setattr(
        llm_mod, "_safe_init",
        lambda cls, model: type("F", (), {
            "name": cls.name, "model": "fake",
            "complete": lambda *a, **k: "x",
        })(),
    )
    c = LLMClient()
    assert c.provider_name == "anthropic"


def test_explicit_override_wins(clean_env, monkeypatch):
    """COACH_LLM_PROVIDER=openai forces OpenAI even when Anthropic key
    is also set — escape hatch for users who want to A/B."""
    clean_env.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
    clean_env.setenv("OPENAI_API_KEY", "sk-fake")
    clean_env.setenv("COACH_LLM_PROVIDER", "openai")
    monkeypatch.setattr(
        llm_mod, "_safe_init",
        lambda cls, model: type("F", (), {
            "name": cls.name, "model": "fake",
            "complete": lambda *a, **k: "x",
        })(),
    )
    c = LLMClient()
    assert c.provider_name == "openai"


def test_provider_failure_degrades_to_stub(clean_env, monkeypatch):
    """If the real provider throws (rate limit, network, auth) the call
    silently falls back to the stub — the coaching loop never stalls
    because the LLM hiccupped."""
    clean_env.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")

    class _Boom:
        name = "anthropic"
        model = "claude-fake"
        def complete(self, *a, **k): raise RuntimeError("rate limit")

    monkeypatch.setattr(llm_mod, "_safe_init", lambda cls, model: _Boom())
    c = LLMClient()
    resp = c.complete("[TASK:journal_append]", "event_kind: log\noutcome: done")
    assert resp.used_stub is True
    assert resp.text  # stub always answers


def test_complete_json_routes_through_stub_when_no_provider(clean_env):
    c = LLMClient()
    # [TASK:journal_append] is one the stub knows how to answer with JSON.
    out = c.complete_json("[TASK:journal_append]", "event_kind: log\noutcome: done")
    assert isinstance(out, dict)
    assert "text" in out and "surface" in out


def test_unknown_provider_value_falls_back_to_auto_detect(clean_env, monkeypatch):
    """Garbage in COACH_LLM_PROVIDER shouldn't disable the LLM — we
    should fall through to auto-detect rather than going stub-only."""
    clean_env.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
    clean_env.setenv("COACH_LLM_PROVIDER", "groq")  # not a real value here

    class _Fake:
        name = "anthropic"
        model = "claude-fake"
        def complete(self, *a, **k): return "ok"

    monkeypatch.setattr(llm_mod, "_safe_init", lambda cls, model: _Fake())
    c = LLMClient()
    assert c.provider_name == "anthropic"
