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

from . import variety
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
from .push import PushDelivery, LoggingPushDelivery
from .store import Store

# Forward reference type-only — see __init__ for `journal` kwarg.
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .journal import CoachJournalAuthor


# ---------------------------------------------------------------------------
# Decision engine — does it make sense to nudge RIGHT NOW?
# ---------------------------------------------------------------------------

@dataclass
class TimingDecision:
    should_fire: bool
    reason: str
    fire_at: datetime | None = None
    expected_window_minutes: int = 30
    # 'full' = prescribe the planned session
    # 'minimum' = invoke the 2-minute-rule fallback (Atomic Habits ch.13)
    # Decided here so the LLM author writes accordingly.
    shape: str = "full"


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
        push: PushDelivery | None = None,
        journal: "CoachJournalAuthor | None" = None,
    ) -> None:
        self.store = store
        self.llm = llm
        self.persona = persona
        self.calendar = calendar
        self.healthkit = healthkit
        self.push: PushDelivery = push or LoggingPushDelivery()
        # Journal is optional so the engine can be used in isolation in
        # tests; when present, nudge authoring conditions on it.
        self.journal = journal

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
        # 0) Pause (v2): the user explicitly asked for silence. Respect it
        #    absolutely — pause means pause, the coach doesn't lecture.
        program = self.store.get_program(user_id)
        if program and program.paused_until is not None and now < program.paused_until:
            return TimingDecision(False, "program paused — coach is silent until resume")

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

        # 5) Receptivity heuristic from HealthKit + recent outcomes.
        #    Low sleep, low steps, or last outcome=partial/not_now → 2-minute
        #    rule: ask for the minimum dose so the user does SOMETHING rather
        #    than nothing (Atomic Habits ch.13 / Section 3.4).
        signals = self.healthkit.recent_signals(user_id, now - timedelta(hours=12))
        sig_summary = ", ".join(f"{s.kind}={s.value}" for s in signals[:3]) or "no recent signals"

        shape = "full"
        if recent:
            last = recent[0]
            if last.outcome in (NudgeOutcome.PARTIAL, NudgeOutcome.NOT_NOW, NudgeOutcome.BUSY):
                shape = "minimum"

        # Signal-driven scale-down: low sleep (<6h) OR a recent workout in
        # the last 12h means receptivity is low. Ask small.
        for s in signals:
            if s.kind == "sleep_hours" and s.value < 6:
                shape = "minimum"
            if s.kind == "workout":  # already trained recently
                shape = "minimum"

        # Readiness Engine (Feature 1): if this morning's HealthKit recovery
        # score put the user in a rest/easy band, ask for the minimum dose
        # regardless of the calendar — the body's signal overrides the plan.
        readiness = self.store.get_readiness(user_id)
        if readiness is not None and readiness.band in ("rest", "easy"):
            shape = "minimum"
            sig_summary = f"readiness={readiness.score}({readiness.band}); " + sig_summary

        # 6) Fire — at the *opportunity*, not "right now blindly".
        fire_at = max(now, slot.start - timedelta(minutes=15))
        reason = f"calendar_gap@{slot.start:%H:%M}({slot.minutes}m), shape={shape}, signals[{sig_summary}]"
        return TimingDecision(
            should_fire=True,
            reason=reason,
            fire_at=fire_at,
            expected_window_minutes=min(slot.minutes, 90),
            shape=shape,
        )

    # -- CONTENT ----------------------------------------------------------

    def author_nudge_text(
        self,
        action: AtomicAction,
        session: Session | None,
        reason: str,
        user_id: str,
        shape: str = "full",
    ) -> dict | None:
        """
        Ask the LLM to write the nudge in the persona's voice, then run the
        variety guard. If the candidate looks too similar to recent nudges,
        re-roll ONCE with explicit avoid-this guidance. If still bad, return
        None — silence is a valid output (Rubric D3).

        `shape='minimum'` triggers the 2-minute-rule framing (ch.13) — ask
        for the minimum_dose, not the full prescription.
        """
        recent_bodies = [n.body for n in self.store.recent_nudges(user_id, limit=8)]
        identity = self.store.get_identity_for_user(user_id)
        identity_line = identity.statement if identity else ""

        # The narrative memory — the thing that makes this a coach who knows
        # the user, not a tracker that fills in templates. When the journal
        # has entries the LLM gets to reference patterns, language the user
        # used, prior friction. When it's empty we still produce a nudge.
        journal_context = (
            self.journal.recent_context_block(user_id, n=8) if self.journal else ""
        )

        def _roll(extra: str = "") -> dict:
            shape_guidance = (
                "  - SHAPE=minimum: this is the 2-minute-rule fallback. Ask for the\n"
                "    MINIMUM dose only (see action.minimum_dose). The point is to\n"
                "    show up at all — DO NOT prescribe the full session.\n"
                if shape == "minimum"
                else "  - SHAPE=full: prescribe the planned session — specific lifts, sets, reps, load.\n"
            )
            journal_block = (
                "\n\nYOUR PRIVATE JOURNAL ON THIS USER (most recent last) — "
                "reference what you've noticed; never quote it verbatim:\n"
                f"{journal_context}\n"
                if journal_context
                else ""
            )
            system = (
                f"[TASK:nudge_text]\n"
                f"You are the user's domain coach.\n"
                f"Voice: {self.persona.voice}\n"
                f"{journal_block}\n"
                "Write a SINGLE push notification (under 220 chars) that:\n"
                f"{shape_guidance}"
                "  - Uses an implementation intention: \"WHEN [cue], I WILL [behavior] AT [location]\".\n"
                "  - Casts the ask as a vote for the user's identity statement (do not quote it verbatim).\n"
                "  - If the journal contains a relevant prior observation (e.g. friction, "
                "a partial last session, a thing the user wrote back), let it shape the "
                "ask — don't generate a one-size message a tracker would.\n"
                "  - Carries one of these flavors at random — pick a different one each time:\n"
                "    [direct prescription] [reframe / lower the bar] [challenge / earn it]\n"
                "    [curiosity question]   [environmental cue]      [data callback to last session].\n"
                "  - NEVER opens with the same template.\n"
                "  - No moralizing. No 'journey'. No emojis."
                + (("\n\n" + extra) if extra else "")
            )
            action_line = action.description
            cue = action.cue or "right now"
            location = action.location or "wherever you train"
            body_brief = ""
            if session:
                body_brief = " | ".join(
                    f"{e.name} {e.sets}x{e.reps}" + (f"@{int(e.load_lb)}" if e.load_lb else "")
                    for e in session.exercises
                )
            user_msg = (
                f"shape: {shape}\n"
                f"identity: {identity_line}\n"
                f"action: {action.title}\n"
                f"prescription: {action_line}\n"
                f"minimum_dose: {action.minimum_dose or '(none)'}\n"
                f"session_brief: {body_brief}\n"
                f"cue: {cue}\n"
                f"location: {location}\n"
                f"timing_reason: {reason}\n"
                f"variety_seed: {random.randint(0, 10_000)}"
            )
            try:
                return self.llm.complete_json(system, user_msg, max_tokens=400, task="NUDGE")
            except Exception:
                if shape == "minimum" and action.minimum_dose:
                    fallback_body = (
                        f"Bad-day plan: {action.minimum_dose}. "
                        f"{cue.capitalize()} — that still counts."
                    )
                else:
                    fallback_body = f"{action.title} — {action_line}. {cue.capitalize()}, start."
                return {
                    "headline": "It's the moment.",
                    "body": fallback_body,
                    "implementation_intention":
                        f"When {cue}, I will start {action.title} at {location}.",
                }

        cand = _roll()
        verdict = variety.check(cand.get("body", ""), recent_bodies)
        if verdict.accept:
            return cand

        # One re-roll with explicit avoid guidance.
        avoid_block = "AVOID THESE OPENINGS AND PHRASINGS — they were used recently:\n" + \
                      "\n".join(f"  - {a}" for a in verdict.avoid_phrases)
        cand2 = _roll(extra=avoid_block)
        verdict2 = variety.check(cand2.get("body", ""), recent_bodies)
        if verdict2.accept:
            return cand2
        return None  # silence — better than repetition

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
        body = self.author_nudge_text(
            action, session, decision.reason, user_id, shape=decision.shape,
        )
        if body is None:
            # Variety guard refused — silence (Rubric D3 + D2).
            return None
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
        # Hand off to the push transport. LoggingPushDelivery prints; APNs in prod.
        try:
            self.push.deliver(user_id=user_id, nudge=nudge)
        except Exception:
            pass  # transport failure must not lose the nudge — it's already persisted
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
