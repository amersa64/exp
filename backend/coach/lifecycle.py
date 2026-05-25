"""
The master loop (Section 4.1) — the entire ballgame.

INTAKE → PROGRAM → PROMPT → EXECUTE → REPORT → ADAPT, then back to PROMPT.

This module wires the persona, the nudge engine, the calendar/HealthKit,
the store, and the world together. Read it top-to-bottom — it's the spine.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from . import safety
from .integrations import CalendarClient, HealthKitClient
from .journal import CoachJournalAuthor
from .llm import LLMClient
from .models import (
    AtomicAction,
    Habit,
    Identity,
    Milestone,
    Nudge,
    NudgeOutcome,
    ProgramState,
    Session,
    TrackingKind,
    TrackingSpec,
    UserProfile,
    VerifiedEvent,
    WorldState,
)
from .nudge import NudgeEngine
from .personas import PERSONAS
from .personas.base import IntakeQuestion, Persona
from .store import Store


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class FollowUp:
    """A pending question the coach owes the user about a past nudge."""
    nudge_id: str
    action_title: str
    prompt: str


class Coach:
    """
    The brain — instantiated per (user, domain).

    Holds NO request-state of its own; everything goes through the Store
    (Rubric A1 — persistence is real, not a chat-session illusion).
    """

    def __init__(
        self,
        user_id: str,
        domain: str,
        store: Store,
        llm: LLMClient,
        calendar: CalendarClient,
        healthkit: HealthKitClient,
    ) -> None:
        if domain not in PERSONAS:
            raise ValueError(
                f"No persona for domain '{domain}'. v1 ships fitness only — "
                "see Section 10 (scope) and Section 4.2 (authoring new personas)."
            )
        self.user_id = user_id
        self.domain = domain
        self.persona: Persona = PERSONAS[domain]
        self.store = store
        self.llm = llm
        self.calendar = calendar
        self.healthkit = healthkit
        self.journal = CoachJournalAuthor(store, llm)
        self.nudge_engine = NudgeEngine(
            store, llm, self.persona, calendar, healthkit,
            journal=self.journal,
        )

    # ---- small helper used everywhere we journal ----
    def _identity_statement(self) -> str | None:
        ident = self.store.get_identity_for_user(self.user_id)
        return ident.statement if ident else None

    # =========================================================================
    # STAGE 1 — INTAKE  (Section 4.1.1, Rubric B1)
    # =========================================================================

    def intake_questions(self) -> list[IntakeQuestion]:
        profile = self.store.get_profile(self.user_id)
        return self.persona.intake_questions(profile)

    def record_intake(self, answers: dict[str, str]) -> tuple[UserProfile, str | None]:
        """
        Take the user's intake answers, run them through the safety filter,
        derive a structured profile via the LLM persona, and persist it.

        Returns (profile, handoff_message_or_None).
        """
        for v in answers.values():
            sig = safety.scan(v)
            if sig:
                return (
                    UserProfile(user_id=self.user_id, domain=self.domain, answers=answers),
                    sig.handoff,
                )

        profile = self.store.get_profile(self.user_id) or UserProfile(
            user_id=self.user_id, domain=self.domain
        )
        profile.answers.update(answers)

        # Use the LLM to derive a structured profile from the free-text answers.
        system = (
            "[TASK:derive_profile]\n"
            f"You are a {self.domain} coach reviewing intake answers.\n"
            f"Voice: {self.persona.voice}\n"
            "Return JSON with keys: derived (object of typed fields), summary (one sentence)."
        )
        user_msg = "Answers:\n" + "\n".join(f"{k}: {v}" for k, v in answers.items())
        derived = self.llm.complete_json(system, user_msg, max_tokens=400)
        profile.derived.update(derived.get("derived", {}))
        profile.updated_at = _now()
        self.store.save_profile(profile)

        # First journal entry: the coach's initial impression. This kicks off
        # the narrative memory that every subsequent LLM call will read from.
        self.journal.append(
            user_id=self.user_id,
            kind="intake",
            event={
                "answers_summary": ", ".join(
                    f"{k}={v[:60]}" for k, v in answers.items()
                )[:400],
                "derived": str(profile.derived)[:300],
            },
            identity_statement=self._identity_statement(),
        )
        return profile, None

    # =========================================================================
    # STAGE 2 — PROGRAM (Section 4.1.2, Rubric B2/B4)
    # =========================================================================

    def build_program(self, identity_statement: str) -> tuple[Identity, list[Milestone], list[Habit], ProgramState]:
        profile = self.store.get_profile(self.user_id)
        if not profile:
            raise RuntimeError("INTAKE must run before PROGRAM. See Section 4.1.")

        anchor = (profile.answers.get("anchor_habit") or "").strip() or None
        identity = Identity(
            user_id=self.user_id,
            statement=identity_statement,
            domain=self.domain,
            anchor_habit=anchor,
        )
        self.store.save_identity(identity)

        program, milestones, habits = self.persona.build_program(profile)
        # Wire parent ids.
        for m in milestones:
            m.parent_identity_id = identity.id
            self.store.save_milestone(m)
        for h in habits:
            # Ensure parent_milestone_id points to a real milestone we just saved.
            if not any(m.id == h.parent_milestone_id for m in milestones):
                h.parent_milestone_id = milestones[0].id
            self.store.save_habit(h)
        self.store.save_program(program)

        # Create the World on first program. After this, growth is only via grow().
        existing_world = self.store.get_world(self.user_id)
        if existing_world is None:
            world = WorldState(user_id=self.user_id, theme=self.persona.world_theme)
            self.store.save_world(world)  # creation-time save, no growth event required
        return identity, milestones, habits, program

    # =========================================================================
    # STAGE 3 — PROMPT  (Section 4.1.3 — actually mints atomic actions and tries to fire)
    # =========================================================================

    def prepare_next_action(self) -> tuple[AtomicAction, Session]:
        profile = self.store.get_profile(self.user_id)
        program = self.store.get_program(self.user_id)
        if not (profile and program):
            raise RuntimeError("PROGRAM stage missing. See Section 4.1.")
        habits = [h for h in self.store.all_habits() if h.active]
        if not habits:
            raise RuntimeError("No active habits — PROGRAM stage didn't seed any.")
        habit = habits[0]

        session = self.persona.next_session(program, profile)

        # Atomic Habits ch.5 + ch.13: ground the action in an implementation
        # intention (cue + location) and a minimum-dose variant. The persona's
        # intake collected the anchor + location; we surface them here so they
        # ride along to the iOS client (Train tab + nudge body) and the LLM
        # nudge author has real strings to work with rather than placeholders.
        answers = profile.answers
        anchor = (answers.get("anchor_habit") or "").strip()
        location = (answers.get("training_location") or "").strip()
        cue = (
            f"right after {anchor}" if anchor
            else "when your next 45-min calendar gap opens"
        )
        # Minimum dose = first exercise, one set, half-reps. The 2-minute
        # version of the session — done on a bad day, this still counts as
        # showing up and reinforces identity.
        first = session.exercises[0]
        min_reps = max(1, first.reps // 2)
        load_str = f" @ {int(first.load_lb)}lb" if first.load_lb else ""
        minimum_dose = f"just 1 set of {first.name} x{min_reps}{load_str} — that's it"

        action = AtomicAction(
            title=f"{session.name} — strength session",
            description=" | ".join(
                f"{e.name} {e.sets}x{e.reps}" + (f" @ {int(e.load_lb)}lb" if e.load_lb else "")
                for e in session.exercises
            ),
            tracking=TrackingSpec(kind=TrackingKind.BINARY),
            parent_habit_id=habit.id,
            cue=cue,
            location=location or None,
            minimum_dose=minimum_dose,
            expected_minutes=session.expected_minutes,
        )
        self.store.save_action(action)
        return action, session

    def try_nudge(self, now: datetime | None = None) -> Nudge | None:
        now = now or _now()
        action, session = self.prepare_next_action()
        return self.nudge_engine.maybe_fire(self.user_id, action, session, now)

    def log_session(
        self,
        action_id: str,
        outcome: NudgeOutcome,
        friction_note: str | None = None,
        now: datetime | None = None,
    ) -> tuple[Nudge, list[str], str | None]:
        """
        User-initiated session log — closes the loop without an APNs nudge.

        Mints a synthetic Nudge marked as already-fired so the rest of the
        REPORT → ADAPT path (record_report → grow → adapt) is unchanged.
        """
        if friction_note:
            sig = safety.scan(friction_note)
            if sig:
                action = self.store.get_action(action_id)
                if not action:
                    raise ValueError(f"unknown action {action_id}")
                return Nudge(
                    user_id=self.user_id, action_id=action_id,
                    fire_window_until=now or _now(),
                    headline="(self-log handed off for safety)",
                    body=action.description,
                    outcome=outcome,
                    outcome_at=now or _now(),
                    friction_note=friction_note,
                    fired_because="self-log",
                ), [], sig.handoff

        action = self.store.get_action(action_id)
        if not action:
            raise ValueError(f"unknown action {action_id}")

        moment = now or _now()
        nudge = Nudge(
            user_id=self.user_id,
            action_id=action.id,
            fired_at=moment,
            fire_window_until=moment,
            headline=action.title,
            body=action.description,
            fired_because="self-log",
        )
        self.store.save_nudge(nudge)
        return self.record_report(nudge.id, outcome, friction_note)

    # =========================================================================
    # STAGE 4 — EXECUTE (Section 4.1.4, Rubric A3 / F2)
    # =========================================================================

    def execute_in_calendar(self, action: AtomicAction, now: datetime | None = None) -> dict:
        """
        Time-block the prescribed behavior. This is the moment the agent stops
        being a chatbot (Section 8 — "puts a real event on a real calendar").
        """
        now = now or _now()
        from datetime import time as _t

        earliest = max(now, datetime.combine(now.date(), _t(7, 0), tzinfo=now.tzinfo))
        latest = datetime.combine(now.date(), _t(22, 0), tzinfo=now.tzinfo)
        slot = self.calendar.find_free_slot(
            self.user_id, earliest, latest, action.expected_minutes
        )
        if slot is None:
            return {"blocked": False, "reason": "no free slot today"}
        ev = self.calendar.block(
            self.user_id, action.title, slot.start, action.expected_minutes
        )
        action.prescribed_for = ev.start
        self.store.save_action(action)
        return {
            "blocked": True,
            "calendar_event_id": ev.id,
            "start": ev.start.isoformat(),
            "end": ev.end.isoformat(),
        }

    # =========================================================================
    # STAGE 5 — REPORT (Section 4.1.5, Rubric A4 / D5)
    # =========================================================================

    def record_report(
        self,
        nudge_id: str,
        outcome: NudgeOutcome,
        friction_note: str | None = None,
    ) -> tuple[Nudge, list[str], str | None]:
        """
        The one-tap reply lands here. Returns (updated_nudge, world_ripples, handoff_or_None).

        Critical: a 'done' report is precisely the kind of source the world's
        verification principle accepts (Section 9.1, source='report').
        """
        nudge = self.store.get_nudge(nudge_id)
        if not nudge:
            raise ValueError(f"unknown nudge {nudge_id}")
        if friction_note:
            sig = safety.scan(friction_note)
            if sig:
                nudge.friction_note = friction_note
                nudge.outcome = outcome
                nudge.outcome_at = _now()
                self.store.save_nudge(nudge)
                return nudge, [], sig.handoff

        nudge.outcome = outcome
        nudge.outcome_at = _now()
        nudge.friction_note = friction_note
        self.store.save_nudge(nudge)

        ripples: list[str] = []
        if outcome == NudgeOutcome.DONE:
            ripples = self._grow_world_from_report(nudge)

        # Append an observational entry. This is where pattern recognition
        # lives: the coach notices "third partial in a row on Lower B" or
        # "user wrote 'back tight' — flag for substitution next time".
        action = self.store.get_action(nudge.action_id)
        self.journal.append(
            user_id=self.user_id,
            kind="reply" if friction_note else "log",
            event={
                "action_title": (action.title if action else "(unknown)"),
                "outcome": outcome.value,
                "friction_note": friction_note or "(none)",
                "ripples": ripples or "(no growth — non-done outcome)",
            },
            identity_statement=self._identity_statement(),
        )
        return nudge, ripples, None

    def _grow_world_from_report(self, nudge: Nudge) -> list[str]:
        action = self.store.get_action(nudge.action_id)
        if not action:
            return []
        event = VerifiedEvent(
            user_id=self.user_id,
            action_id=action.id,
            nudge_id=nudge.id,
            source="report",
        )
        self.store.save_verified_event(event)
        world = self.store.get_world(self.user_id) or WorldState(
            user_id=self.user_id, theme=self.persona.world_theme
        )
        ripples = world.grow(event, action)
        self.store.save_world(world, growth_event=event)
        return ripples

    def record_sensor_verification(
        self,
        action_id: str,
        sensor: str,
        payload: dict | None = None,
    ) -> list[str]:
        """Verification via HealthKit/Calendar signal (Section 9.1, source='sensor')."""
        action = self.store.get_action(action_id)
        if not action:
            return []
        event = VerifiedEvent(
            user_id=self.user_id,
            action_id=action.id,
            nudge_id=None,
            source="sensor",
            sensor=sensor,
            payload=payload or {},
        )
        self.store.save_verified_event(event)
        world = self.store.get_world(self.user_id) or WorldState(
            user_id=self.user_id, theme=self.persona.world_theme
        )
        ripples = world.grow(event, action)
        self.store.save_world(world, growth_event=event)
        return ripples

    # =========================================================================
    # COACH RESPONSE — short LLM-authored reply to a user's friction note.
    # =========================================================================

    def compose_coach_response(
        self,
        outcome: NudgeOutcome,
        friction_note: str | None,
        action_title: str | None = None,
    ) -> str | None:
        """
        Generate a one-line reply in the coach's voice acknowledging what
        the user said. Returns None when there's nothing to acknowledge
        (clean done with no note) so callers don't have to special-case.

        Conditioned on the journal: a real LLM will reference past patterns
        ('this is the third time you mentioned the back — let's swap to
        goblet next session'). The stub returns a canned-but-honest reply.
        """
        if not friction_note and outcome == NudgeOutcome.DONE:
            return None  # Nothing extra to say; the ripples already speak.
        identity = self.store.get_identity_for_user(self.user_id)
        system = (
            "[TASK:coach_response]\n"
            f"You are the user's domain coach. Voice: {self.persona.voice}\n"
            "Write ONE short sentence (<= 160 chars) replying to what the user "
            "just reported. Acknowledge specifically what they wrote. No platitudes. "
            "No 'journey'. No emojis. If you spot a pattern from the journal, name it.\n"
        )
        journal_block = self.journal.recent_context_block(self.user_id, n=8)
        if journal_block:
            system += "\nYour private journal on this user:\n" + journal_block + "\n"
        user_msg = (
            f"identity: {identity.statement if identity else '(none)'}\n"
            f"action: {action_title or '(unknown)'}\n"
            f"outcome: {outcome.value}\n"
            f"friction: {friction_note or '(none)'}"
        )
        try:
            resp = self.llm.complete(system, user_msg, max_tokens=200)
            text = resp.text.strip().strip('"').strip()
            return text or None
        except Exception:
            return None

    # =========================================================================
    # STAGE 6 — ADAPT (Section 4.1.6, Rubric B3 — THE thing that makes us a coach)
    # =========================================================================

    def adapt(self) -> str:
        """Re-plan the program based on the most recent reports."""
        program = self.store.get_program(self.user_id)
        if not program:
            return "no program yet"
        recents = []
        for n in self.store.recent_nudges(self.user_id, limit=5):
            if n.outcome == NudgeOutcome.PENDING:
                continue
            action = self.store.get_action(n.action_id)
            session_name = action.title if action else ""
            recents.append({
                "outcome": n.outcome.value,
                "friction": n.friction_note,
                "session_name": session_name,
            })
        new_program, technical_rationale = self.persona.progression_rules(program, recents)
        self.store.save_program(new_program)

        # The Python rule produces a true-but-mechanical sentence ("+10 squat,
        # +5 bench, +5 row"). The LLM rewrites that into the coach's voice
        # conditioned on the journal — so the user reads "Bumping squat 10
        # because you cleared all three sets at 95 with room to spare and your
        # one partial was sleep-related, not strength-related" instead of a
        # rule output. Falls back to the technical sentence if the LLM call
        # fails, so the API contract never loses content.
        narrative = self._compose_adapt_narrative(
            technical_rationale=technical_rationale,
            recents=recents,
            new_progression=new_program.progression,
        )

        # Journal the adaptation in the coach's voice — gives the next nudge
        # context for "why are we doing this load this week?"
        self.journal.append(
            user_id=self.user_id,
            kind="adapt",
            event={
                "rationale": narrative,
                "technical_rationale": technical_rationale,
                "progression": str(new_program.progression)[:300],
                "recent_outcomes": ", ".join(r["outcome"] for r in recents) or "(none)",
            },
            identity_statement=self._identity_statement(),
        )
        return narrative

    def _compose_adapt_narrative(
        self,
        technical_rationale: str,
        recents: list[dict],
        new_progression: dict,
    ) -> str:
        """Turn the deterministic Python rationale into a coach-voice sentence."""
        identity = self.store.get_identity_for_user(self.user_id)
        latest_outcome = recents[0]["outcome"] if recents else "(none)"
        latest_friction = recents[0].get("friction") if recents else None
        system = (
            "[TASK:adapt_narrative]\n"
            f"You are the user's domain coach. Voice: {self.persona.voice}\n"
            "Rewrite the technical programming rationale in ONE sentence "
            "(<= 200 chars) in your own voice. Reference the actual reason "
            "the load is moving (or holding). If the journal shows a relevant "
            "pattern (sleep, friction, recent partials), name it. No moralizing."
        )
        journal_block = self.journal.recent_context_block(self.user_id, n=8)
        if journal_block:
            system += "\n\nYour private journal on this user:\n" + journal_block
        user_msg = (
            f"identity: {identity.statement if identity else '(none)'}\n"
            f"technical_rationale: {technical_rationale}\n"
            f"latest_outcome: {latest_outcome}\n"
            f"latest_friction: {latest_friction or '(none)'}\n"
            f"new_progression: {new_progression}"
        )
        try:
            text = self.llm.complete(system, user_msg, max_tokens=200).text.strip().strip('"')
            return text or technical_rationale
        except Exception:
            return technical_rationale

    # =========================================================================
    # LOOP-CLOSING (Rubric A4) — what did I ask you to do? did you do it?
    # =========================================================================

    def open_followups(self, now: datetime | None = None) -> list[FollowUp]:
        now = now or _now()
        self.nudge_engine.sweep_ignored(self.user_id, now)
        out: list[FollowUp] = []
        for n in self.store.recent_nudges(self.user_id, limit=10):
            if n.outcome in (NudgeOutcome.IGNORED, NudgeOutcome.NOT_NOW, NudgeOutcome.BUSY):
                if n.friction_note is None:  # not yet followed up on
                    action = self.store.get_action(n.action_id)
                    title = action.title if action else "(unknown)"
                    out.append(FollowUp(
                        nudge_id=n.id,
                        action_title=title,
                        prompt=(
                            f"Earlier I asked you about: {title}. "
                            "What happened — done, partial, or did something get in the way? "
                            "If it slipped, no judgement; tell me what blocked it and when we should reschedule."
                        ),
                    ))
        return out
