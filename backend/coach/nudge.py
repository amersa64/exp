"""
The nudge engine (Section 7) — where the product lives or dies.

Three jobs:
  1) CONTEXTUAL TIMING (Rubric D1): decide WHEN to fire, by detecting M+A windows
     using calendar gaps, HealthKit signals, recent nudge outcomes, and a
     frequency budget. Not "9am every day."
  2) VARIED CONTENT (Rubric D2): ask the LLM to author the nudge text fresh, in
     the persona's voice, carrying the actual prescription + implementation
     intention (Rubric D4). Never the same templated ping twice.
  3) RESTRAINT (Rubric D3): silence is a valid output. Back off when ignored.
     Hard frequency cap per day. The product respects the user's attention.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Optional

from .integrations import (
    CalendarClient,
    FreeSlot,
    HealthKitClient,
)
from .llm import LLMClient
from .models import (
    AtomicAction,
    Nudge,
    NudgeOutcome,
    Session,
)
from .personas.base import Persona
from .store import Store


# ---------------------------------------------------------------------------
# Decision engine — does it make sense to nudge RIGHT NOW?
# ---------------------------------------------------------------------------

@dataclass
class TimingDecision:
    should_fire: bool
    reason: str
    fire_at: datetime | None = None
    expected_window_minutes: int = 30


class NudgeEngine:
    # Restraint knobs (Rubric D3). Tune from real outcomes, never raise blindly.
    DAILY_NUDGE_CAP = 2
    MIN_GAP_BETWEEN_NUDGES_MIN = 90
    BACKOFF_AFTER_IGNORED = 2          # after 2 ignored in a row → skip a day
    BACKOFF_AFTER_NOT_NOW = 1          # one "not now" → wait at least 3h

    def __init__(
        self,
        store: Store,
        llm: LLMClient,
        persona: Persona,
        calendar: CalendarClient,
        healthkit: HealthKitClient,
    ) -> None:
        self.store = store
        self.llm = llm
        self.persona = persona
        self.calendar = calendar
        self.healthkit = healthkit

    # -- TIMING ------------------------------------------------------------

    def decide_timing(
        self,
        user_id: str,
        action: AtomicAction,
        now: datetime,
    ) -> TimingDecision:
        """
        JITAI decision (Section 3.3): is the user reachable AND receptive AND
        does an opportunity window exist?
        """
        # 1) Restraint: have we already fired enough today?
        todays = [
            n for n in self.store.recent_nudges(user_id, limit=20)
            if n.fired_at.date() == now.date()
        ]
        if len(todays) >= self.DAILY_NUDGE_CAP:
            return TimingDecision(False, "daily nudge cap reached — silence is a feature")

        # 2) Restraint: last nudge cooldown.
        if todays:
            last = max(todays, key=lambda n: n.fired_at)
            since = (now - last.fired_at).total_seconds() / 60
            if since < self.MIN_GAP_BETWEEN_NUDGES_MIN:
                return TimingDecision(False, f"cooldown — last nudge {int(since)}m ago")
            if last.outcome == NudgeOutcome.NOT_NOW and since < 180:
                return TimingDecision(False, "user said not_now recently — back off")

        # 3) Back-off after repeated ignores (Rubric D3).
        recent = self.store.recent_nudges(user_id, limit=6)
        ignored_streak = 0
        for n in recent:
            if n.outcome == NudgeOutcome.IGNORED:
                ignored_streak += 1
            else:
                break
        if ignored_streak >= self.BACKOFF_AFTER_IGNORED:
            # Skip a calendar day after repeated ignores.
            last_fired = recent[0].fired_at if recent else now
            if (now - last_fired) < timedelta(hours=24):
                return TimingDecision(False, f"{ignored_streak} ignored in a row — taking a day off")

        # 4) Opportunity: find a real free slot on the calendar.
        earliest = max(now, datetime.combine(now.date(), time(7, 0), tzinfo=now.tzinfo))
        latest = datetime.combine(now.date(), time(22, 0), tzinfo=now.tzinfo)
        slot = self.calendar.find_free_slot(
            user_id, earliest, latest, action.expected_minutes
        )
        if slot is None:
            return TimingDecision(False, "no free slot on the calendar today — try tomorrow")

        # 5) Receptivity heuristic from HealthKit: low sleep → soften, low steps →
        #    a movement-prescription is a fit; high recent exertion → propose the
        #    smaller version (the 2-minute rule, Section 3.4).
        # For v0 we only use these signals as REASON metadata; the decision is GO.
        signals = self.healthkit.recent_signals(user_id, now - timedelta(hours=12))
        sig_summary = ", ".join(f"{s.kind}={s.value}" for s in signals[:3]) or "no recent signals"

        # 6) Fire — at the *opportunity*, not "right now blindly".
        fire_at = max(now, slot.start - timedelta(minutes=15))
        reason = f"calendar_gap@{slot.start:%H:%M}({slot.minutes}m), signals[{sig_summary}]"
        return TimingDecision(
            should_fire=True,
            reason=reason,
            fire_at=fire_at,
            expected_window_minutes=min(slot.minutes, 90),
        )

    # -- CONTENT ----------------------------------------------------------

    def author_nudge_text(self, action: AtomicAction, session: Session | None, reason: str) -> dict:
        """
        Ask the LLM to write the nudge in the persona's voice.

        The prompt deliberately injects variety and constrains length so the
        text is one tight push notification, carrying the actual prescription.
        """
        system = (
            f"[TASK:nudge_text]\n"
            f"You are the user's domain coach.\n"
            f"Voice: {self.persona.voice}\n\n"
            "Write a SINGLE push notification (under 220 chars) that:\n"
            "  - Names the specific action, not a category.\n"
            "  - Uses an implementation intention (\"when X, I will Y\").\n"
            "  - Carries one of these flavors at random — pick a different one each time:\n"
            "    [direct prescription] [reframe / lower the bar] [challenge / earn it]\n"
            "    [curiosity question]   [environmental cue]      [data callback to last session].\n"
            "  - NEVER opens with the same template.\n"
            "  - No moralizing. No 'journey'. No emojis."
        )
        action_line = action.description
        cue = action.cue or "right now"
        body_brief = ""
        if session:
            body_brief = " | ".join(
                f"{e.name} {e.sets}x{e.reps}" + (f"@{int(e.load_lb)}" if e.load_lb else "")
                for e in session.exercises
            )
        user_msg = (
            f"action: {action.title}\n"
            f"prescription: {action_line}\n"
            f"session_brief: {body_brief}\n"
            f"cue: {cue}\n"
            f"timing_reason: {reason}\n"
            f"variety_seed: {random.randint(0, 10_000)}"
        )
        try:
            return self.llm.complete_json(system, user_msg, max_tokens=400)
        except Exception:
            return {
                "headline": "It's the moment.",
                "body": f"{action.title} — {action_line}. {cue.capitalize()}, start.",
                "implementation_intention": f"When this nudge fires, I will start {action.title}.",
            }

    # -- FIRE -------------------------------------------------------------

    def maybe_fire(
        self,
        user_id: str,
        action: AtomicAction,
        session: Session | None,
        now: datetime,
    ) -> Nudge | None:
        decision = self.decide_timing(user_id, action, now)
        if not decision.should_fire:
            return None
        body = self.author_nudge_text(action, session, decision.reason)
        nudge = Nudge(
            user_id=user_id,
            action_id=action.id,
            fired_at=decision.fire_at or now,
            fire_window_until=(decision.fire_at or now) + timedelta(minutes=decision.expected_window_minutes),
            headline=body.get("headline", "It's the moment."),
            body=body.get("body", action.description),
            implementation_intention=body.get("implementation_intention"),
            fired_because=decision.reason,
        )
        self.store.save_nudge(nudge)
        return nudge

    # -- AUTO-IGNORE SWEEPER ---------------------------------------------

    def sweep_ignored(self, user_id: str, now: datetime) -> int:
        """
        Mark any pending nudges past their fire window as IGNORED.
        Should be called periodically by the scheduler.
        """
        count = 0
        for n in self.store.recent_nudges(user_id, limit=50):
            if n.outcome == NudgeOutcome.PENDING and now > n.fire_window_until:
                n.outcome = NudgeOutcome.IGNORED
                n.outcome_at = now
                self.store.save_nudge(n)
                count += 1
        return count
