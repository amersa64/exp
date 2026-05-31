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
from . import recovery, vitals
from .models import (
    AtomicAction,
    ExerciseLog,
    Habit,
    Identity,
    Milestone,
    Nudge,
    NudgeOutcome,
    ProgramState,
    ReadinessSnapshot,
    Session,
    TrackingKind,
    TrackingSpec,
    TrainingPlace,
    UserProfile,
    VerifiedEvent,
    VitalSample,
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
        # Pin the value types — without this, OpenAI tends to return lists for
        # multi-valued fields ('injuries': ['knee', 'shoulder']) where Anthropic
        # collapses to a string. Either shape parses now (see UserProfile.derived)
        # but downstream prompt assembly is simpler when values are scalar.
        system = (
            "[TASK:derive_profile]\n"
            f"You are a {self.domain} coach reviewing intake answers.\n"
            f"Voice: {self.persona.voice}\n"
            "Return JSON with keys: derived (object of typed fields), summary (one sentence).\n"
            "Each value in `derived` MUST be a scalar — string, integer, or float. "
            "Do not return lists, objects, or null. Collapse multi-value notes into "
            "a single string (e.g. injuries: \"left knee, mild shoulder\")."
        )
        user_msg = "Answers:\n" + "\n".join(f"{k}: {v}" for k, v in answers.items())
        derived = self.llm.complete_json(system, user_msg, max_tokens=400, task="DERIVE_PROFILE")
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
        top_sets: dict[str, dict[str, float]] | None = None,
        exercise_logs: dict[str, ExerciseLog] | None = None,
    ) -> tuple[Nudge, list[str], str | None]:
        """
        User-initiated session log — closes the loop without an APNs nudge.

        Mints a synthetic Nudge marked as already-fired so the rest of the
        REPORT → ADAPT path (record_report → grow → adapt) is unchanged.

        `exercise_logs` is the per-exercise breakdown (Section 5) — each
        prescribed lift's outcome + actual reps/load. The session-level
        `outcome` here is the rollup computed by the caller; we stash both
        so the brain can see the granular picture later.
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
                    exercise_logs=exercise_logs or {},
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
        return self.record_report(
            nudge.id, outcome, friction_note,
            top_sets=top_sets, exercise_logs=exercise_logs,
        )

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
        top_sets: dict[str, dict[str, float]] | None = None,
        exercise_logs: dict[str, ExerciseLog] | None = None,
    ) -> tuple[Nudge, list[str], str | None]:
        """
        The one-tap reply lands here. Returns (updated_nudge, world_ripples, handoff_or_None).

        Critical: a 'done' report is precisely the kind of source the world's
        verification principle accepts (Section 9.1, source='report').

        `top_sets` is the structured calibration log — keyed by lift slot
        (e.g. "squat") with value {reps, load_lb}. Only sent by the iOS log
        sheet during the calibration phase; ignored / empty for normal logs.

        `exercise_logs` is the per-exercise breakdown captured by the new
        Train log sheet (Section 5: each exercise is the atomic action).
        Keyed by exercise name. Stashed on the Nudge so the brain can read
        the granular picture; the rollup `outcome` is what drives world growth.
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
                if top_sets:
                    nudge.top_sets = top_sets
                if exercise_logs:
                    nudge.exercise_logs = exercise_logs
                self.store.save_nudge(nudge)
                return nudge, [], sig.handoff

        nudge.outcome = outcome
        nudge.outcome_at = _now()
        nudge.friction_note = friction_note
        if top_sets:
            nudge.top_sets = top_sets
        if exercise_logs:
            nudge.exercise_logs = exercise_logs
        self.store.save_nudge(nudge)

        ripples: list[str] = []
        if outcome == NudgeOutcome.DONE:
            ripples = self._grow_world_from_report(nudge)

        # Append an observational entry. This is where pattern recognition
        # lives: the coach notices "third partial in a row on Lower B" or
        # "user wrote 'back tight' — flag for substitution next time". The
        # per-exercise breakdown lets the coach catch finer patterns ("user
        # has skipped pullups three sessions running").
        action = self.store.get_action(nudge.action_id)
        self.journal.append(
            user_id=self.user_id,
            kind="reply" if friction_note else "log",
            event={
                "action_title": (action.title if action else "(unknown)"),
                "outcome": outcome.value,
                "friction_note": friction_note or "(none)",
                "ripples": ripples or "(no growth — non-done outcome)",
                "exercise_logs": exercise_logs or "(none)",
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
            resp = self.llm.complete(system, user_msg, max_tokens=200, task="COACH_RESPONSE")
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
        profile = self.store.get_profile(self.user_id)
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
                # Calibration-aware fields. Personas that don't use them
                # (current: every persona except strength) simply ignore
                # them; the dict has no contract beyond "carries the keys
                # the persona reads".
                "top_sets": n.top_sets or {},
                "profile": profile,
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
            text = self.llm.complete(system, user_msg, max_tokens=200, task="ADAPT").text.strip().strip('"')
            return text or technical_rationale
        except Exception:
            return technical_rationale

    # =========================================================================
    # IPHONE SIGNALS (Section 8.1) — the sensors that let the coach act without
    # being asked. Readiness (sleep/HR/HRV), gym geofence, workout auto-log.
    # =========================================================================

    # ---- Feature 1: Readiness Engine ----------------------------------------

    def record_readiness(
        self,
        *,
        sleep_hours: float | None = None,
        resting_hr: float | None = None,
        hrv_ms: float | None = None,
        resting_hr_baseline: float | None = None,
        hrv_baseline: float | None = None,
        at: datetime | None = None,
    ) -> ReadinessSnapshot:
        """Take this morning's HealthKit recovery signals, score them, persist.

        The SCORE + BAND are derived here (coach.recovery) so the rule is one
        deterministic Python function, not Swift. We keep only the latest
        snapshot per user — readiness is a today-thing, not a history we mine.
        """
        snap = ReadinessSnapshot(
            user_id=self.user_id,
            at=at or _now(),
            sleep_hours=sleep_hours,
            resting_hr=resting_hr,
            hrv_ms=hrv_ms,
            resting_hr_baseline=resting_hr_baseline,
            hrv_baseline=hrv_baseline,
        )
        snap.score, snap.band = recovery.score_readiness(snap)

        # Smarter multi-day recovery: pull the last week of sleep from the
        # vitals time series and dock the score for accumulated debt, so a run
        # of short nights drags readiness down even after one decent sleep.
        debt = vitals.sleep_debt(self._sleep_series_points(nights=7))
        if debt is not None:
            snap.sleep_debt_h = debt
            penalty = recovery.multiday_penalty(debt)
            if penalty:
                snap.score = max(0, snap.score - penalty)
                snap.band = recovery.readiness_band(snap.score)
        self.store.save_readiness(snap)

        # Journal it so the coach's voice everywhere (nudges, adapt) can lean
        # on "you've been under-slept all week" without re-deriving it.
        self.journal.append(
            user_id=self.user_id,
            kind="readiness",
            event={
                "score": snap.score,
                "band": snap.band,
                "sleep_hours": snap.sleep_hours if snap.sleep_hours is not None else "(none)",
                "resting_hr": snap.resting_hr if snap.resting_hr is not None else "(none)",
                "hrv_ms": snap.hrv_ms if snap.hrv_ms is not None else "(none)",
            },
            identity_statement=self._identity_statement(),
        )
        return snap

    def latest_readiness(self) -> ReadinessSnapshot | None:
        return self.store.get_readiness(self.user_id)

    # ---- Broad vitals ingestion + trends ------------------------------------

    # Retention window for the rolling time series. 90 days is enough for a
    # weight trajectory and a cardio-fitness trend without unbounded growth.
    VITALS_RETENTION_DAYS = 90

    def record_vitals(self, samples: list[VitalSample]) -> int:
        """Store a batch of HealthKit readings (any metrics) and prune old data.

        Only known metric keys (coach.vitals.METRICS) are kept — the client may
        send more than we model; we drop the rest rather than store noise.
        """
        known = [s for s in samples if s.metric in vitals.METRICS]
        if not known:
            return 0
        n = self.store.save_vital_samples(self.user_id, known)
        cutoff = _now() - timedelta(days=self.VITALS_RETENTION_DAYS)
        self.store.prune_vitals(self.user_id, cutoff)
        return n

    def _sleep_series_points(self, nights: int = 7) -> list[tuple[datetime, float]]:
        since = _now() - timedelta(days=nights + 1)
        series = self.store.vitals_series(self.user_id, "sleep_asleep_h", since=since)
        return [(s.at, s.value) for s in series]

    def vitals_summary(self) -> dict:
        """Dashboard payload: a trend summary per metric the user has + derived
        insights (weight trajectory, relative strength). Everything iPhone-safe;
        Watch metrics appear only if some device wrote them."""
        since = _now() - timedelta(days=self.VITALS_RETENTION_DAYS)
        metrics_out: list[dict] = []
        for metric in self.store.vitals_metrics(self.user_id):
            series = self.store.vitals_series(self.user_id, metric, since=since)
            summary = vitals.summarize_metric(metric, [(s.at, s.value) for s in series])
            if summary:
                metrics_out.append(summary)
        # Stable, useful ordering: body first, then sleep, core, optional.
        tier_rank = {"body": 0, "sleep": 1, "core": 2, "optional": 3}
        metrics_out.sort(key=lambda m: (tier_rank.get(m["tier"], 9), m["label"]))
        return {
            "metrics": metrics_out,
            "insights": self._vitals_insights(),
        }

    def _vitals_insights(self) -> list[dict]:
        """Cross-metric reads the coach surfaces in plain language."""
        out: list[dict] = []
        since = _now() - timedelta(days=self.VITALS_RETENTION_DAYS)

        # Weight trajectory — slope per week + a 4-week projection.
        weight = self.store.vitals_series(self.user_id, "body_mass_kg", since=since)
        if len(weight) >= 2:
            pts = [(s.at, s.value) for s in weight]
            slope_day = vitals.linear_slope_per_day(pts)
            if slope_day is not None and abs(slope_day) > 1e-4:
                per_week = slope_day * 7
                current = pts[-1][1]
                projected = current + slope_day * 28
                direction = "down" if per_week < 0 else "up"
                out.append({
                    "kind": "weight_trajectory",
                    "title": "Weight trend",
                    "detail": (
                        f"{abs(per_week):.2f} kg/week {direction}. "
                        f"At this rate you're ~{projected:.1f} kg in 4 weeks "
                        f"(now {current:.1f})."
                    ),
                    "direction": direction,
                })

        # Relative strength — best calibration est-1RM vs current bodyweight.
        bw = self.store.latest_vital(self.user_id, "body_mass_kg")
        program = self.store.get_program(self.user_id)
        if bw and program and program.calibration_results:
            bw_lb = bw.value * 2.2046226
            for slot in ("squat", "deadlift", "bench"):
                res = program.calibration_results.get(slot)
                if not res:
                    continue
                est = res.get("est_1rm_lb")
                if not isinstance(est, (int, float)) or bw_lb <= 0:
                    continue
                ratio = est / bw_lb
                out.append({
                    "kind": "relative_strength",
                    "title": f"{slot.capitalize()} vs bodyweight",
                    "detail": f"{ratio:.2f}× bodyweight ({int(est)} lb est. 1RM at {bw.value:.1f} kg).",
                    "direction": "up",
                })

        return out

    def readiness_directive(self) -> tuple[ReadinessSnapshot | None, str]:
        """(snapshot, directive) where directive ∈ {full, reduced, rest}.

        No snapshot, or an 'unknown' band → 'full' (we never block training on
        missing data). This is what /session/next reads to shape the ask.
        """
        snap = self.latest_readiness()
        if snap is None or snap.band == "unknown":
            return snap, "full"
        return snap, recovery.band_directive(snap.band)

    def readiness_note(self, snap: ReadinessSnapshot) -> str | None:
        """A short, specific, coach-voiced line about today's readiness.

        Deterministic on purpose: it names the actual numbers that moved the
        score, so it reads like a coach who looked at your watch rather than a
        horoscope. Returns None for 'unknown' (nothing honest to say).
        """
        if snap.band == "unknown":
            return None

        bits: list[str] = []
        if snap.sleep_hours is not None:
            bits.append(f"slept {snap.sleep_hours:.1f}h")
        if snap.resting_hr is not None:
            base = snap.resting_hr_baseline
            if base:
                delta = round(snap.resting_hr - base)
                if delta >= 2:
                    bits.append(f"resting HR +{delta} over your normal")
                elif delta <= -2:
                    bits.append(f"resting HR {abs(delta)} under your normal")
                else:
                    bits.append("resting HR right at your normal")
            else:
                bits.append(f"resting HR {round(snap.resting_hr)}")
        if snap.hrv_ms is not None and snap.hrv_baseline:
            drop = (snap.hrv_baseline - snap.hrv_ms) / snap.hrv_baseline
            if drop >= 0.15:
                bits.append("HRV down")
            elif drop <= -0.15:
                bits.append("HRV up")
        signal_phrase = ", ".join(bits) if bits else "today's numbers"

        # Multi-day context — name the debt when it's the thing dragging you down.
        debt_suffix = ""
        if snap.sleep_debt_h and snap.sleep_debt_h > 3.0:
            debt_suffix = f" You're carrying ~{snap.sleep_debt_h:.0f}h of sleep debt this week."

        if snap.band == "rest":
            return (f"Readiness {snap.score} — {signal_phrase}.{debt_suffix} Today's a recovery day; "
                    "the minimum dose still counts as a vote. Don't chase load.")
        if snap.band == "easy":
            return (f"Readiness {snap.score} — {signal_phrase}.{debt_suffix} We'll move, but trim it: "
                    "hold the loads, drop a set if it's grinding.")
        if snap.band == "primed":
            return (f"Readiness {snap.score} — {signal_phrase}. You're primed. "
                    "Green light on the full session.")
        # ready
        return f"Readiness {snap.score} — {signal_phrase}.{debt_suffix} Good to train as planned."

    # ---- Feature 2: Gym Radar (learned geofence) ----------------------------

    def observe_training_place(self, lat: float, lon: float) -> TrainingPlace:
        """Fold one coordinate observation (posted when a session starts/logs)
        into the learned training place. The brain learns where you train —
        we never ask."""
        place = self.store.get_place(self.user_id)
        updated = recovery.update_place_centroid(
            place, user_id=self.user_id, lat=lat, lon=lon
        )
        self.store.save_place(updated)
        return updated

    def learned_place(self) -> TrainingPlace | None:
        return self.store.get_place(self.user_id)

    def record_location_event(
        self, event: str, lat: float | None = None, lon: float | None = None,
    ) -> dict:
        """The phone crossed the gym geofence. Return what the coach should do.

        event="arrived" → surface today's session, with a contextual line.
        event="departed" → if nothing's been logged today, prompt a log.

        Restraint (Rubric D3): we don't re-prompt if the daily session is
        already done, and we say nothing on a departure we can't act on.
        """
        place = self.store.get_place(self.user_id)
        label = place.label if place else "your gym"

        done_today = self._has_logged_today()

        if event == "arrived":
            if done_today:
                return {
                    "surface_session": False,
                    "coach_line": f"Already in the books today — you're at {label} for the bonus.",
                }
            return {
                "surface_session": True,
                "coach_line": f"You're at {label}. Today's session is loaded and ready — start when you are.",
            }

        if event == "departed":
            if done_today:
                return {"surface_session": False, "coach_line": None}
            return {
                "surface_session": False,
                "coach_line": f"Leaving {label}? If you trained, log it so it counts. If not, no judgement — tomorrow.",
            }

        return {"surface_session": False, "coach_line": None}

    def _has_logged_today(self, now: datetime | None = None) -> bool:
        now = now or _now()
        today = now.date()
        for n in self.store.recent_nudges(self.user_id, limit=10):
            if n.outcome == NudgeOutcome.DONE and n.outcome_at and n.outcome_at.date() == today:
                return True
        return False

    # ---- Feature 3: Auto-log from an Apple Health workout -------------------

    def autolog_from_workout(
        self,
        action_id: str,
        *,
        duration_min: float | None = None,
        active_kcal: float | None = None,
        avg_hr: float | None = None,
        workout_type: str | None = None,
        ended_at: datetime | None = None,
    ) -> tuple[Nudge, list[str]]:
        """Close the loop from a HealthKit workout — no typing required.

        HealthKit saw a workout that overlaps the prescribed window. We log the
        session DONE and grow the world via a SENSOR verification (Section 9.1,
        source='sensor' — the strongest kind), enriching the verified event
        with the real duration / calories / heart rate. Returns the synthetic
        nudge + the world ripples; the caller composes the spoken reply + adapt.
        """
        action = self.store.get_action(action_id)
        if not action:
            raise ValueError(f"unknown action {action_id}")

        moment = ended_at or _now()
        # A synthetic, already-resolved nudge so the REPORT loop (followups,
        # adapt, journal) sees a real done event — but growth comes from the
        # sensor path below, not record_report, so the world grows exactly once.
        payload_bits = []
        if duration_min is not None:
            payload_bits.append(f"{round(duration_min)} min")
        if active_kcal is not None:
            payload_bits.append(f"{round(active_kcal)} kcal")
        if avg_hr is not None:
            payload_bits.append(f"avg HR {round(avg_hr)}")
        enrich = " · ".join(payload_bits)

        nudge = Nudge(
            user_id=self.user_id,
            action_id=action.id,
            fired_at=moment,
            fire_window_until=moment,
            headline=action.title,
            body=action.description,
            outcome=NudgeOutcome.DONE,
            outcome_at=moment,
            friction_note=(f"auto-logged from Apple Health: {enrich}" if enrich else "auto-logged from Apple Health"),
            fired_because="healthkit.autolog",
        )
        self.store.save_nudge(nudge)

        payload: dict[str, str | int | float] = {}
        if duration_min is not None:
            payload["duration_min"] = round(duration_min, 1)
        if active_kcal is not None:
            payload["active_kcal"] = round(active_kcal, 1)
        if avg_hr is not None:
            payload["avg_hr"] = round(avg_hr, 1)
        if workout_type:
            payload["workout_type"] = workout_type

        ripples = self.record_sensor_verification(
            action.id, "healthkit.workout", payload,
        )

        self.journal.append(
            user_id=self.user_id,
            kind="autolog",
            event={
                "action_title": action.title,
                "enrichment": enrich or "(no metrics)",
                "ripples": ripples or "(no growth)",
            },
            identity_statement=self._identity_statement(),
        )
        return nudge, ripples

    # =========================================================================
    # COACH TAB (v2) — the brain decides ONE shape the user should see now.
    # Quiet / Prescription / Slip / Return / Pause. The Marcus-voiced lines are
    # deterministic on purpose: the design brief says the moat surfaces (slip /
    # return) ship with hand-authored copy, never relying on generation.
    # =========================================================================

    # Thresholds (v2 design). Tune from real outcomes.
    SLIP_MISS_THRESHOLD = 2          # consecutive misses → slip shape
    RETURN_ABSENCE_DAYS = 5          # days since last verified event → return shape
    _MISS_OUTCOMES = (
        NudgeOutcome.SKIPPED, NudgeOutcome.IGNORED,
        NudgeOutcome.BUSY, NudgeOutcome.NOT_NOW,
    )

    def pause_program(self, days: int, now: datetime | None = None) -> datetime:
        """Pause the program for `days` (Shape E / 'give me a week'). Returns the
        resume moment. The scheduler should suppress nudges while paused."""
        now = now or _now()
        program = self.store.get_program(self.user_id)
        if not program:
            raise RuntimeError("no program to pause")
        program.paused_until = now + timedelta(days=days)
        self.store.save_program(program)
        self.journal.append(
            user_id=self.user_id, kind="pause",
            event={"days": days, "until": program.paused_until.isoformat()},
            identity_statement=self._identity_statement(),
        )
        return program.paused_until

    def resume_program(self) -> None:
        program = self.store.get_program(self.user_id)
        if program and program.paused_until is not None:
            program.paused_until = None
            self.store.save_program(program)

    def _days_since_last_verified(self, now: datetime) -> int | None:
        events = self.store.verified_events_for(self.user_id)
        if not events:
            return None
        return (now.date() - events[-1].at.date()).days

    def _consecutive_misses(self) -> int:
        """Leading run of missed outcomes among recent resolved nudges. A
        done/partial breaks the run (the body backed it up)."""
        streak = 0
        for n in self.store.recent_nudges(self.user_id, limit=10):
            if n.outcome == NudgeOutcome.PENDING:
                continue
            if n.outcome in self._MISS_OUTCOMES:
                streak += 1
            else:
                break
        return streak

    def coach_today(self, now: datetime | None = None) -> dict:
        """The single shape the Coach tab renders. See design/v2/screens/01."""
        now = now or _now()
        program = self.store.get_program(self.user_id)
        world = self.store.get_world(self.user_id)
        votes = world.identity_votes if world else 0
        followups = [
            {"nudge_id": f.nudge_id, "title": f.action_title, "prompt": f.prompt}
            for f in self.open_followups(now)
        ]

        def payload(shape: str, line: str, **extra) -> dict:
            return {"shape": shape, "coach_line": line, "votes": votes,
                    "followups": followups, **extra}

        # No program yet — the user hasn't finished onboarding.
        if not program:
            return payload("quiet", "Finish setup and I'll have your first session.")

        # E — Pause. Quiet wins over everything; pause means pause.
        if program.paused_until is not None and now < program.paused_until:
            resume = program.paused_until
            when = self._weekday_phrase(resume, now)
            return payload("pause", f"Paused. Back {when}.",
                           resume_on=resume.isoformat())

        # D — Return after absence.
        days_away = self._days_since_last_verified(now)
        if days_away is not None and days_away >= self.RETURN_ABSENCE_DAYS:
            return payload("return", f"Haven't seen you in {days_away} days. Still in?",
                           days_away=days_away)

        # Prescription / minimum dose — both need today's action.
        try:
            action, session = self.prepare_next_action()
        except RuntimeError:
            return payload("quiet", "Nothing prescribed yet.")

        # C — Slip. Two in a row → the intervention: name it, offer the minimum.
        if self._consecutive_misses() >= self.SLIP_MISS_THRESHOLD:
            dose = action.minimum_dose or "one easy set. That's it."
            return payload(
                "slip",
                f"Two in a row. Something's getting in the way. Today: {dose} Tap in after.",
                action_id=action.id, session_name=session.name,
                minimum_dose=action.minimum_dose,
            )

        # B — Prescription. Name the session + the script.
        cue = (action.cue or "when the moment opens").strip()
        loc = (action.location or "").strip()
        script = f"{cue.capitalize()}, {loc}." if loc else f"{cue.capitalize()}."
        return payload(
            "prescription",
            f"{session.name} today. {script} Tap in when it's done.",
            action_id=action.id, session_name=session.name,
            minimum_dose=action.minimum_dose,
        )

    @staticmethod
    def _weekday_phrase(target: datetime, now: datetime) -> str:
        """'Sunday' / 'tomorrow' / 'in 3 days' — how Marcus would say a date."""
        delta = (target.date() - now.date()).days
        if delta <= 0:
            return "now"
        if delta == 1:
            return "tomorrow"
        if delta < 7:
            return target.strftime("%A")
        return f"in {delta} days"

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
