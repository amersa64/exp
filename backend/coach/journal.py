"""
The coach's narrative memory of a user.

After every meaningful event — intake answered, session logged, reply
received, program adapted — we ask the LLM to write ONE sentence into the
coach's private journal. The full journal is fed back as context for every
future LLM call (nudge authoring, adaptation reasoning, observation
surfacing). This is the layer that turns "an app with state" into "an
agent with memory" (Principle 2.2).

The journal is intentionally free-text, not structured fields. Pattern
recognition lives in language, not in columns. A real coach doesn't
think "user_id=alice / outcome=partial / count=3"; they think "Alice
keeps missing Wednesdays — what's different about Wednesdays?" The
journal is the place that thought belongs.

Offline-safe: if no ANTHROPIC_API_KEY is set the LLM client falls through
to a deterministic stub (see llm._stub_completion). The stub writes
realistic-shaped sentences so the rest of the system runs end-to-end.
"""

from __future__ import annotations

from typing import Any

from .llm import LLMClient
from .models import CoachJournal, JournalEntry
from .store import Store


# How many prior entries we include as context for the next observation.
# Tune this against actual token cost — 10 is enough to spot week-scale
# patterns without ballooning the prompt.
RECENT_CONTEXT_WINDOW = 10


class CoachJournalAuthor:
    """Writes new entries into the journal via the LLM."""

    def __init__(self, store: Store, llm: LLMClient) -> None:
        self.store = store
        self.llm = llm

    def get_or_create(self, user_id: str) -> CoachJournal:
        j = self.store.get_journal(user_id)
        if j is None:
            j = CoachJournal(user_id=user_id)
            self.store.save_journal(j)
        return j

    def append(
        self,
        user_id: str,
        kind: str,
        event: dict[str, Any],
        identity_statement: str | None = None,
    ) -> JournalEntry:
        """
        Compose one observational sentence about a freshly-occurred event and
        append it to the user's journal. Returns the new entry.

        `kind` is the event category (intake, log, reply, adapt, observation).
        `event` is a small dict the prompt can render verbatim (kept narrow
        so the system prompt stays cheap and the LLM doesn't have to guess
        what mattered). `identity_statement` is the user's chosen "I am ..."
        — included so the coach's voice anchors to who the user is becoming,
        not just what they did.
        """
        journal = self.get_or_create(user_id)
        prior = journal.recent(RECENT_CONTEXT_WINDOW)

        system = (
            "[TASK:journal_append]\n"
            "You are a strength coach keeping a PRIVATE journal about ONE specific "
            "client. After each meaningful event you write a single sentence noting "
            "what you observed, a pattern you suspect, or what you'd do differently "
            "next time. Voice: direct, technical, never preachy. Never moralize. "
            "Never use the word 'journey'.\n\n"
            "Output JSON with three fields:\n"
            "  text: ONE sentence (<= 240 chars). The observation.\n"
            "  surface: true ONLY if this is something the user themselves should "
            "hear right now (a pattern they wouldn't see on their own, or a "
            "noticing they'd value). False by default — most notes are private.\n"
            "  reason_for_surface: short string if surface=true, else null."
        )

        prior_block = (
            "\n".join(f"  - [{e.kind}] {e.text}" for e in prior)
            if prior
            else "  (no prior entries — this is the first)"
        )
        event_block = "\n".join(f"  {k}: {v}" for k, v in event.items())
        user_msg = (
            f"client identity: {identity_statement or '(not yet set)'}\n"
            f"event_kind: {kind}\n\n"
            f"recent journal (most recent last):\n{prior_block}\n\n"
            f"event_details:\n{event_block}"
        )
        try:
            raw = self.llm.complete_json(system, user_msg, max_tokens=300, task="JOURNAL")
        except Exception:
            raw = {"text": f"{kind} event recorded.", "surface": False, "reason_for_surface": None}

        entry = JournalEntry(
            kind=kind,
            text=str(raw.get("text", "")).strip() or f"{kind} event recorded.",
            surface=bool(raw.get("surface", False)),
            reason_for_surface=raw.get("reason_for_surface") or None,
        )
        journal.append(entry)
        self.store.save_journal(journal)
        return entry

    def recent_context_block(self, user_id: str, n: int = RECENT_CONTEXT_WINDOW) -> str:
        """
        Format the recent journal as a single text block for inclusion in
        other LLM prompts (nudge authoring, adaptation reasoning). Empty
        string when the journal is empty — let the caller decide whether
        to mention "no history yet" in their own prompt.
        """
        journal = self.store.get_journal(user_id)
        if journal is None or not journal.entries:
            return ""
        lines = [f"  - [{e.kind} @ {e.at:%Y-%m-%d %H:%M}] {e.text}"
                 for e in journal.recent(n)]
        return "\n".join(lines)

    def latest_surfaced(self, user_id: str) -> JournalEntry | None:
        journal = self.store.get_journal(user_id)
        return journal.latest_surfaced() if journal else None
