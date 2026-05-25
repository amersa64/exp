"""
HTTP layer for the brain.

Auth is intentionally NOT in this build — the spec is for a personal copilot
and the brief never asked for multi-tenant. When that day comes, an OAuth
bearer middleware drops in here. For now, the user_id comes from a header so
the iOS client and curl-driven tests both work.

Every endpoint maps directly to a Coach method — no business logic lives here.
This layer is purely a port. If you find yourself writing coaching logic in a
route handler, move it to `coach/lifecycle.py`.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from coach.integrations import StubCalendarClient, StubHealthKitClient
from coach.lifecycle import Coach
from coach.llm import LLMClient
from coach.models import NudgeOutcome
from coach.push import LoggingPushDelivery
from coach.scheduler import Scheduler, active_users_from_store
from coach.store import Store


# ---- bootstrap singletons --------------------------------------------------

DB_PATH = os.environ.get("COACH_DB", "coach.db")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.store = Store(DB_PATH)
    app.state.llm = LLMClient()
    app.state.calendar = StubCalendarClient()
    app.state.healthkit = StubHealthKitClient()
    app.state.push = LoggingPushDelivery()
    app.state.scheduler = Scheduler(
        store=app.state.store,
        llm=app.state.llm,
        calendar=app.state.calendar,
        healthkit=app.state.healthkit,
        push=app.state.push,
        active_users=active_users_from_store(app.state.store),
    )
    yield


app = FastAPI(title="The Coach — brain", lifespan=lifespan)


def _coach_for(user_id: str, domain: str = "fitness") -> Coach:
    s = app.state
    c = Coach(user_id, domain, s.store, s.llm, s.calendar, s.healthkit)
    c.nudge_engine.push = s.push
    return c


def _uid(x_user_id: str | None) -> str:
    if not x_user_id:
        raise HTTPException(401, "X-User-Id header required")
    return x_user_id


# ---- request/response models ----------------------------------------------

class IntakeSubmit(BaseModel):
    answers: dict[str, str]
    identity_statement: str | None = None  # if present, also runs PROGRAM stage


class IntakeResponse(BaseModel):
    summary: str
    handoff: str | None = None
    program_built: bool = False


class ReplyBody(BaseModel):
    outcome: NudgeOutcome
    friction: str | None = None


class HealthSignalBody(BaseModel):
    kind: str
    value: float
    at: datetime | None = None
    metadata: dict[str, str] = {}


class PushRegister(BaseModel):
    token: str
    platform: str = "ios"


class LogSessionBody(BaseModel):
    outcome: NudgeOutcome
    friction: str | None = None


# ---- routes ----------------------------------------------------------------

@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/intake/questions")
def intake_questions(x_user_id: str = Header(default=None)) -> dict[str, Any]:
    coach = _coach_for(_uid(x_user_id))
    qs = coach.intake_questions()
    return {"questions": [{"key": q.key, "q": q.q} for q in qs]}


@app.post("/intake/submit", response_model=IntakeResponse)
def intake_submit(body: IntakeSubmit, x_user_id: str = Header(default=None)) -> IntakeResponse:
    coach = _coach_for(_uid(x_user_id))
    profile, handoff = coach.record_intake(body.answers)
    if handoff:
        return IntakeResponse(summary="Held — see handoff.", handoff=handoff)
    program_built = False
    if body.identity_statement:
        coach.build_program(body.identity_statement)
        program_built = True
    return IntakeResponse(
        summary=profile.derived.get("summary", "Profile saved."),
        program_built=program_built,
    )


@app.get("/world")
def get_world(x_user_id: str = Header(default=None)) -> dict[str, Any]:
    w = app.state.store.get_world(_uid(x_user_id))
    if w is None:
        raise HTTPException(404, "no world yet — finish intake + program")
    return w.model_dump()


@app.get("/identity")
def get_identity(x_user_id: str = Header(default=None)) -> dict[str, Any]:
    ident = app.state.store.get_identity_for_user(_uid(x_user_id))
    if ident is None:
        raise HTTPException(404, "no identity yet — finish intake + program")
    return ident.model_dump()


@app.get("/milestones")
def get_milestones(x_user_id: str = Header(default=None)) -> dict[str, Any]:
    ms = app.state.store.list_milestones_for_user(_uid(x_user_id))
    return {"milestones": [m.model_dump() for m in ms]}


@app.get("/followups")
def get_followups(x_user_id: str = Header(default=None)) -> dict[str, Any]:
    coach = _coach_for(_uid(x_user_id))
    fs = coach.open_followups()
    return {"followups": [
        {"nudge_id": f.nudge_id, "action_title": f.action_title, "prompt": f.prompt}
        for f in fs
    ]}


@app.post("/nudge/{nudge_id}/reply")
def reply(nudge_id: str, body: ReplyBody, x_user_id: str = Header(default=None)) -> dict[str, Any]:
    coach = _coach_for(_uid(x_user_id))
    nudge, ripples, handoff = coach.record_report(nudge_id, body.outcome, body.friction)
    rationale = coach.adapt()
    return {
        "ok": True,
        "ripples": ripples,
        "handoff": handoff,
        "adaptation": rationale,
        "outcome": nudge.outcome.value,
    }


@app.post("/healthkit/signal")
def healthkit_signal(body: HealthSignalBody, x_user_id: str = Header(default=None)) -> dict[str, Any]:
    user_id = _uid(x_user_id)
    from coach.integrations import HealthSignal
    sig = HealthSignal(
        user_id=user_id,
        kind=body.kind,
        at=body.at or datetime.now(timezone.utc),
        value=body.value,
        metadata=body.metadata,
    )
    app.state.healthkit.seed(sig)
    # If it's a workout, try to verify against the most-recent prescribed action.
    ripples: list[str] = []
    if body.kind == "workout":
        coach = _coach_for(user_id)
        # Find the most recent prescribed action.
        actions = app.state.store.all_actions()
        actions = [a for a in actions if a.parent_habit_id]
        if actions:
            latest = max(actions, key=lambda a: a.prescribed_for or datetime.min.replace(tzinfo=timezone.utc))
            ripples = coach.record_sensor_verification(
                latest.id, "healthkit.workout",
                {"duration_min": body.value, **body.metadata},
            )
    return {"ok": True, "ripples": ripples}


@app.post("/push/register")
def push_register(body: PushRegister, x_user_id: str = Header(default=None)) -> dict[str, str]:
    app.state.push.register_device(_uid(x_user_id), body.token, body.platform)
    return {"ok": "registered"}


@app.get("/session/next")
def session_next(x_user_id: str = Header(default=None)) -> dict[str, Any]:
    """
    The next prescribed session — what the coach would push if it were the moment.

    Minting via `prepare_next_action` so a real AtomicAction id exists in the
    store; iOS then references that id when logging or scheduling. This is the
    same code path the nudge engine uses, so what the user sees is what would
    have been pushed.
    """
    coach = _coach_for(_uid(x_user_id))
    try:
        action, session = coach.prepare_next_action()
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return {
        "action_id": action.id,
        "action_title": action.title,
        "prescribed_for": action.prescribed_for.isoformat() if action.prescribed_for else None,
        "expected_minutes": session.expected_minutes,
        "cue": action.cue,
        "location": action.location,
        "minimum_dose": action.minimum_dose,
        "session": {
            "name": session.name,
            "expected_minutes": session.expected_minutes,
            "progression_rule": session.progression_rule,
            "exercises": [e.model_dump() for e in session.exercises],
        },
    }


@app.get("/coach/state")
def coach_state(x_user_id: str = Header(default=None)) -> dict[str, Any]:
    """
    Snapshot of what the brain is thinking right now — for the dev pane on iOS
    and for human-readable debugging. NOT a place to add coaching logic.
    """
    user_id = _uid(x_user_id)
    store = app.state.store
    profile = store.get_profile(user_id)
    program = store.get_program(user_id)
    identity = store.get_identity_for_user(user_id)
    nudges = store.recent_nudges(user_id, limit=5)
    coach = _coach_for(user_id)
    followups = coach.open_followups()
    last_nudge = nudges[0] if nudges else None
    return {
        "has_profile": profile is not None,
        "has_program": program is not None,
        "identity_statement": identity.statement if identity else None,
        "identity_anchor": identity.anchor_habit if identity else None,
        "program_name": program.program_name if program else None,
        "session_index": program.session_index if program else 0,
        "last_nudge": (
            {
                "id": last_nudge.id,
                "headline": last_nudge.headline,
                "body": last_nudge.body,
                "implementation_intention": last_nudge.implementation_intention,
                "fired_at": last_nudge.fired_at.isoformat(),
                "fired_because": last_nudge.fired_because,
                "outcome": last_nudge.outcome.value,
            }
            if last_nudge else None
        ),
        "open_followups": [
            {"nudge_id": f.nudge_id, "title": f.action_title, "prompt": f.prompt}
            for f in followups
        ],
    }


@app.post("/dev/tick")
def dev_tick(x_user_id: str = Header(default=None)) -> dict[str, Any]:
    """
    Dev affordance: run a scheduler tick for THIS user and return what the
    brain decided. Lets the iOS app exercise the JITAI loop without APNs.
    Carries no auth because the whole app carries no auth — see top of file.
    """
    user_id = _uid(x_user_id)
    coach = _coach_for(user_id)
    coach.nudge_engine.sweep_ignored(user_id, datetime.now(timezone.utc))
    nudge = coach.try_nudge()
    return {
        "fired": nudge is not None,
        "nudge": (
            {
                "id": nudge.id,
                "headline": nudge.headline,
                "body": nudge.body,
                "implementation_intention": nudge.implementation_intention,
                "fired_because": nudge.fired_because,
            }
            if nudge else None
        ),
    }


@app.post("/session/{action_id}/log")
def session_log(action_id: str, body: LogSessionBody, x_user_id: str = Header(default=None)) -> dict[str, Any]:
    """
    User-initiated session log — closes the loop without an APNs nudge.

    Same downstream effect as POST /nudge/{id}/reply: world grows on 'done',
    program adapts on every report.
    """
    coach = _coach_for(_uid(x_user_id))
    try:
        nudge, ripples, handoff = coach.log_session(action_id, body.outcome, body.friction)
    except ValueError as e:
        raise HTTPException(404, str(e))
    rationale = coach.adapt()
    return {
        "ok": True,
        "ripples": ripples,
        "handoff": handoff,
        "adaptation": rationale,
        "outcome": nudge.outcome.value,
    }


@app.post("/session/{action_id}/schedule")
def session_schedule(action_id: str, x_user_id: str = Header(default=None)) -> dict[str, Any]:
    """Time-block the prescribed session on the calendar (EXECUTE stage)."""
    coach = _coach_for(_uid(x_user_id))
    action = app.state.store.get_action(action_id)
    if not action:
        raise HTTPException(404, f"unknown action {action_id}")
    return coach.execute_in_calendar(action)


@app.post("/scheduler/tick")
def scheduler_tick(now: str | None = None) -> dict[str, Any]:
    """Manually trigger a scheduler tick — for tests + ops. In prod a cron hits this.

    `now` is an optional ISO-8601 timestamp; lets tests pin a deterministic
    moment so the nudge engine's calendar-window logic doesn't depend on
    wall-clock time-of-day.
    """
    from datetime import datetime, timezone
    pinned = None
    if now:
        pinned = datetime.fromisoformat(now)
        if pinned.tzinfo is None:
            pinned = pinned.replace(tzinfo=timezone.utc)
    res = app.state.scheduler.run_tick(now=pinned)
    return {
        "users_evaluated": res.users_evaluated,
        "nudges_fired": [n.id for n in res.nudges_fired],
        "silences": res.silences,
        "followups_owed": res.followups_owed,
    }
