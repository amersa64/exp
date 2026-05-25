"""
LLM client used by intake, programming, nudge-text generation, and adaptation.

Wraps the Anthropic SDK when an API key is present. Falls back to a deterministic
stub LLM so the whole coaching lifecycle remains runnable and testable offline.

The stub is intentionally not a chatbot — it returns canned but structurally
correct responses so the rest of the system can be exercised end-to-end.
"""

from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMResponse:
    text: str
    used_stub: bool


class LLMClient:
    """Thin wrapper; subclasses or the stub path can be swapped in tests."""

    DEFAULT_MODEL = "claude-sonnet-4-6"

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.environ.get("COACH_LLM_MODEL", self.DEFAULT_MODEL)
        self._client = None
        if os.environ.get("ANTHROPIC_API_KEY"):
            try:
                import anthropic  # type: ignore
                self._client = anthropic.Anthropic()
            except Exception:
                self._client = None

    def complete(self, system: str, user: str, max_tokens: int = 600) -> LLMResponse:
        if self._client is None:
            return LLMResponse(text=_stub_completion(system, user), used_stub=True)
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(
            block.text for block in msg.content if getattr(block, "type", "") == "text"
        )
        return LLMResponse(text=text, used_stub=False)

    def complete_json(self, system: str, user: str, max_tokens: int = 800) -> dict[str, Any]:
        """Ask for a JSON object. Falls back to stub on any parse failure."""
        resp = self.complete(
            system=system + "\n\nRespond ONLY with a single JSON object. No prose, no markdown.",
            user=user,
            max_tokens=max_tokens,
        )
        text = resp.text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return json.loads(_stub_completion(system, user))


# ---------------------------------------------------------------------------
# Stub completions — keep the system honest and runnable without a key.
# These are deliberately varied (Section 7.1) and the intake/adapt stubs return
# realistic JSON the persona can ingest.
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
