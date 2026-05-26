"""
LLM client used by intake, programming, nudge-text generation, adaptation,
and the coach journal.

Supports two providers behind one interface:
  - Anthropic Claude (ANTHROPIC_API_KEY)
  - OpenAI         (OPENAI_API_KEY)

Selection rules (in order):
  1) COACH_LLM_PROVIDER env var, if set: must be 'anthropic' or 'openai'.
  2) Whichever key is present in the environment wins. If both are set,
     Anthropic wins (the prompts in this repo were tuned against Claude).
  3) If neither key is present, the client falls through to a deterministic
     stub so the whole coaching lifecycle remains runnable and testable
     offline (Section 8: no required external services).

The stub is intentionally not a chatbot — it returns canned but structurally
correct responses tagged by [TASK:...] markers in the system prompt so the
rest of the system can be exercised end-to-end.
"""

from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class LLMResponse:
    text: str
    used_stub: bool


# ---------------------------------------------------------------------------
# Provider interface — small, deliberately not abstract-class-y. Each
# provider takes a system + user prompt and returns text. JSON-mode is
# handled by the LLMClient by appending a contract sentence to the system
# prompt (and, for OpenAI, opting into native response_format).
# ---------------------------------------------------------------------------

class _Provider(Protocol):
    name: str          # "anthropic" | "openai"
    model: str

    def complete(self, system: str, user: str, max_tokens: int, *, json_mode: bool) -> str: ...


class _AnthropicProvider:
    """Wraps anthropic.Anthropic.messages.create()."""

    name = "anthropic"
    DEFAULT_MODEL = "claude-sonnet-4-6"

    def __init__(self, model: str | None = None) -> None:
        import anthropic  # imported lazily so a missing dep doesn't break tests
        self._sdk = anthropic.Anthropic()
        self.model = model or self.DEFAULT_MODEL

    def complete(self, system: str, user: str, max_tokens: int, *, json_mode: bool) -> str:
        # Anthropic doesn't have a native JSON response_format yet; the
        # caller has already appended a "respond with JSON only" sentence
        # to the system prompt. That contract is enough in practice.
        msg = self._sdk.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(
            block.text for block in msg.content if getattr(block, "type", "") == "text"
        )


class _OpenAIProvider:
    """Wraps openai.OpenAI.chat.completions.create()."""

    name = "openai"
    # gpt-4o-mini balances cost and quality for the journal / nudge volume
    # this app generates (tens of calls per active user per day). Override
    # via COACH_LLM_MODEL when you want gpt-4o, o1, gpt-5, etc.
    DEFAULT_MODEL = "gpt-4o-mini"

    def __init__(self, model: str | None = None) -> None:
        import openai  # lazy import
        self._sdk = openai.OpenAI()
        self.model = model or self.DEFAULT_MODEL

    def complete(self, system: str, user: str, max_tokens: int, *, json_mode: bool) -> str:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
        }
        if json_mode:
            # OpenAI requires that the prompt mention "json" when this is
            # set — the LLMClient.complete_json wrapper guarantees that.
            kwargs["response_format"] = {"type": "json_object"}
        resp = self._sdk.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Provider selection — single chokepoint so the rest of the code never
# has to know which SDK is in use.
# ---------------------------------------------------------------------------

def _select_provider(model: str | None) -> _Provider | None:
    explicit = (os.environ.get("COACH_LLM_PROVIDER") or "").strip().lower()
    has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))
    has_openai = bool(os.environ.get("OPENAI_API_KEY"))

    # Explicit override wins, but only if the matching key is present —
    # otherwise we'd return a provider that crashes on its first call.
    if explicit == "anthropic":
        if not has_anthropic:
            return None
        return _safe_init(_AnthropicProvider, model)
    if explicit == "openai":
        if not has_openai:
            return None
        return _safe_init(_OpenAIProvider, model)
    if explicit:
        # Unknown value — fall through to auto-detect, don't crash.
        pass

    # Auto-detect: Anthropic wins ties because the prompts in this repo
    # were authored against Claude's style. Users can pin OpenAI explicitly
    # via COACH_LLM_PROVIDER if they prefer.
    if has_anthropic:
        return _safe_init(_AnthropicProvider, model)
    if has_openai:
        return _safe_init(_OpenAIProvider, model)
    return None


def _safe_init(cls, model: str | None) -> _Provider | None:
    """SDK import or auth issue should degrade to stub, never crash startup."""
    try:
        return cls(model)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public client — what the rest of the codebase imports.
# ---------------------------------------------------------------------------

class LLMClient:
    """Provider-agnostic façade. Falls through to a stub when no key is set."""

    def __init__(self, model: str | None = None) -> None:
        # COACH_LLM_MODEL lets a user pin a specific model name regardless
        # of provider (e.g. claude-opus-4-1 or gpt-4o). Provider defaults
        # apply when this is unset.
        chosen_model = model or os.environ.get("COACH_LLM_MODEL") or None
        self._provider: _Provider | None = _select_provider(chosen_model)
        # `model` is what /healthz reports — keep it informative whether
        # we ended up on a real provider or the stub.
        self.model = (
            self._provider.model if self._provider
            else (chosen_model or "stub")
        )

    # Backwards-compatible attribute the previous code path used to detect
    # real-vs-stub mode. Keeps callers (and the /healthz route) working
    # without a sweep.
    @property
    def _client(self) -> _Provider | None:
        return self._provider

    @property
    def provider_name(self) -> str:
        return self._provider.name if self._provider else "stub"

    def complete(self, system: str, user: str, max_tokens: int = 600) -> LLMResponse:
        if self._provider is None:
            return LLMResponse(text=_stub_completion(system, user), used_stub=True)
        try:
            text = self._provider.complete(system, user, max_tokens, json_mode=False)
            return LLMResponse(text=text, used_stub=False)
        except Exception:
            # Any provider failure (rate limit, auth, network) silently
            # degrades to the stub — the coaching loop never stalls because
            # the LLM hiccupped.
            return LLMResponse(text=_stub_completion(system, user), used_stub=True)

    def complete_json(self, system: str, user: str, max_tokens: int = 800) -> dict[str, Any]:
        """
        Ask for a JSON object. Falls back to stub on any parse failure.

        We append the "JSON only" contract to the system prompt for both
        providers, AND opt into OpenAI's native response_format when on
        OpenAI. Both belts and suspenders — providers are flaky enough
        about format adherence that overspecifying is correct.
        """
        contract = "\n\nRespond ONLY with a single JSON object. No prose, no markdown."
        full_system = system + contract
        if self._provider is None:
            return json.loads(_stub_completion(system, user))
        try:
            text = self._provider.complete(
                full_system, user, max_tokens, json_mode=True
            ).strip()
            if text.startswith("```"):
                text = text.strip("`")
                if text.lower().startswith("json"):
                    text = text[4:].strip()
            return json.loads(text)
        except Exception:
            return json.loads(_stub_completion(system, user))


# ---------------------------------------------------------------------------
# Stub completions — keep the system honest and runnable without a key.
# These are deliberately varied (Section 7.1) and the intake/adapt stubs
# return realistic JSON the persona can ingest.
# ---------------------------------------------------------------------------

_NUDGE_VOICES_FULL = [
    "{cue_cap}. Shoes by the door, head out for {action}. Tap when you're out the door.",
    "Window's open: {action} at {location}. 20-min version is fine — consistency > intensity.",
    "Quick check — energy 1–5? If 3+: {action}. If 2 or under: bad-day plan instead, no negotiation.",
    "Tomorrow's not a real plan; today is. {cue_cap}: head to {location} for {action}.",
    "Last session you reported it felt easy. Today we earn it: {action} at {location}.",
    "Heads up — gap on your calendar opens soon. {cue_cap}, start {action} at {location}.",
    "Half-rep at half-effort beats a perfect plan you skipped. {action} at {location} — start.",
]

_NUDGE_VOICES_MIN = [
    "Bad-day plan: {min_dose}. {cue_cap} — that's the whole ask.",
    "Don't open the app, open the door. {min_dose}. Showing up is the vote.",
    "Two-minute version today: {min_dose}. {cue_cap}. Tap when done.",
    "Today we keep the streak, not push it. {min_dose} — start.",
]


def _stub_completion(system: str, user: str) -> str:
    """
    Best-effort canned response. Looks at the system prompt for a `[TASK:xxx]` tag
    that the persona/lifecycle code writes, and returns plausible structured output.
    """
    tag = ""
    for line in system.splitlines():
        if line.strip().startswith("[TASK:") and line.strip().endswith("]"):
            tag = line.strip()[6:-1]
            break

    if tag == "intake_questions":
        return json.dumps({
            "questions": [
                {"key": "experience", "q": "How would you describe your strength-training experience — none, novice (less than 6 months consistent), intermediate (1+ year), or advanced?"},
                {"key": "days_per_week", "q": "Realistically — not aspirationally — how many days per week can you train? (2, 3, or 4)"},
                {"key": "injuries", "q": "Any current pain, injuries, or movements you should avoid? Describe them, or 'none'."},
                {"key": "equipment", "q": "What equipment do you have access to? (e.g. full gym, barbell+rack at home, dumbbells only, bodyweight only)"},
                {"key": "baseline_squat", "q": "Roughly, what's the most you can squat for 5 reps with good form? (lb, or 'unsure')"},
            ]
        })

    if tag == "derive_profile":
        return json.dumps({
            "derived": {
                "experience": "novice",
                "days_per_week": 3,
                "injuries": "none",
                "equipment": "barbell+rack",
                "1rm_squat_lb": 135,
            },
            "summary": "Novice lifter, 3 days/week, no injuries, home barbell setup. Linear progression is a fit.",
        })

    if tag == "nudge_text":
        action = _extract_field(user, "action") or "today's session"
        cue = _extract_field(user, "cue") or "right now"
        location = _extract_field(user, "location") or "wherever you train"
        shape = _extract_field(user, "shape") or "full"
        min_dose = _extract_field(user, "minimum_dose") or "show up at all"
        pool = _NUDGE_VOICES_MIN if shape == "minimum" else _NUDGE_VOICES_FULL
        template = random.choice(pool)
        body = template.format(
            action=action, cue=cue, cue_cap=cue.capitalize(),
            location=location, min_dose=min_dose,
        )
        # Implementation intention is always WHEN/I WILL/AT — Atomic Habits ch.5.
        ask = min_dose if shape == "minimum" else action
        return json.dumps({
            "headline": "It's the moment." if shape == "full" else "Bad-day plan.",
            "body": body,
            "implementation_intention":
                f"When {cue}, I will do {ask} at {location}.",
        })

    if tag == "adapt":
        return json.dumps({
            "decision": "hold",
            "rationale": "One data point — wait for a second signal before changing the program.",
            "progression_delta": {},
        })

    if tag == "adapt_narrative":
        # Coach-voice explanation of a programming change. The technical
        # diff is upstream (deterministic Python); this is just the WHY in
        # plain English. Stub keeps it short and concrete; real LLM weaves
        # in the journal.
        rationale = _extract_field(user, "technical_rationale") or ""
        outcome = _extract_field(user, "latest_outcome") or ""
        if outcome == "done":
            base = "Cleared the prescribed work. Earning the next jump."
        elif outcome == "partial":
            base = "Holding loads — repeat this one cleanly before we push."
        else:
            base = "No clean signal this cycle. Holding the program steady."
        return f"{base} ({rationale[:80]})" if rationale else base

    if tag == "coach_response":
        # Short, warm, specific. Acknowledges what the user wrote without
        # platitudes. The real LLM does pattern matching against the journal;
        # the stub just echoes a generic-but-honest reply.
        friction = (_extract_field(user, "friction") or "").strip()
        outcome = (_extract_field(user, "outcome") or "").strip()
        canned = {
            "done":    "Heard. The body of work is what matters — that's another rep on the board.",
            "partial": "That's data, not failure. We hold the load and try again next session.",
            "not_now": "Logged. The coach will back off and aim for the next real window.",
            "busy":    "Acknowledged. No retry today — momentum survives one missed slot.",
            "skipped": "Heard. We don't make up missed sessions; the next one is what matters.",
        }
        body = canned.get(outcome, "Got it.")
        if friction:
            body += f" Noted: \"{friction[:60]}\"."
        return body

    if tag == "journal_append":
        # Stub journal entries — terse, kind-aware, varied enough to read
        # like a real coach taking notes. Never surface=true offline: the
        # decision of "this is worth telling the user" requires real
        # pattern recognition we don't have without the LLM.
        kind = (_extract_field(user, "event_kind") or "event").lower()
        outcome = _extract_field(user, "outcome")
        text_pool = {
            "intake": "First contact — established baseline. Watching for what they actually do vs what they said.",
            "log": f"Logged {outcome or 'something'} — too early to call a pattern; one more data point before adjusting.",
            "reply": "User actually wrote something back — worth more than a button tap. File the language for later.",
            "adapt": "Numeric adjustment applied; will see in the next two sessions whether it lands or asks too much.",
            "tick": "Quiet check-in; nothing earned attention.",
        }
        return json.dumps({
            "text": text_pool.get(kind, f"{kind} event noted."),
            "surface": False,
            "reason_for_surface": None,
        })

    # Generic fallback.
    return "OK."


def _extract_field(text: str, key: str) -> str | None:
    """Tiny helper for stub extraction; not robust, intentionally."""
    needle = f"{key}:"
    if needle in text:
        rest = text.split(needle, 1)[1]
        return rest.splitlines()[0].strip().strip(",")
    return None
