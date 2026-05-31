"""
HTTP layer for the brain.

Auth: a single shared bearer token, opt-in via the COACH_API_TOKEN env var
(see the _auth_gate middleware below). When the token is set, every route
except /healthz requires `Authorization: Bearer <token>`, and the /dev/*
routes are disabled unless COACH_ENABLE_DEV=1. When the token is unset the API
is open — the default for local dev and the test suite. The user_id still
comes from the X-User-Id header (single-tenant; identity, not authorization).

Every endpoint maps directly to a Coach method — no business logic lives here.
This layer is purely a port. If you find yourself writing coaching logic in a
route handler, move it to `coach/lifecycle.py`.
"""

from __future__ import annotations

import hmac
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


# ---- .env autoload --------------------------------------------------------
# Tiny inline loader so the user can put ANTHROPIC_API_KEY in a `.env` at
# the repo root and the backend picks it up no matter how it's launched
# (deploy.sh, raw uvicorn, IDE, tests). Done BEFORE importing anything from
# `coach.*` so the LLM client sees the key during its own import-time setup.
# Avoids adding python-dotenv as a dependency — the format is trivial.
def _load_dotenv() -> None:
    # Skip when pytest is in charge — the test suite scrubs LLM env vars in
    # an autouse fixture (see backend/tests/conftest.py) so every test runs
    # against the deterministic stub. If we re-loaded .env on each test's
    # re-import of api.app we'd silently undo that and start charging the
    # user's API credits for unit tests.
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    # backend/api/app.py → repo root is three parents up.
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        # Don't clobber values already explicitly exported in the shell — the
        # shell wins, which is what users expect from .env semantics.
        if value and key.strip() not in os.environ:
            os.environ[key.strip()] = value


_load_dotenv()


from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from coach.integrations import StubCalendarClient, StubHealthKitClient
from coach.lifecycle import Coach
from coach.llm import LLMClient
from coach.models import NudgeOutcome
from coach.push import make_push
from coach.scheduler import Scheduler, active_users_from_store
from coach.store import make_store


# ---- bootstrap singletons --------------------------------------------------

DB_PATH = os.environ.get("COACH_DB", "coach.db")

log = logging.getLogger("coach.api")

# Shared bearer token. When set, _auth_gate enforces it on every route except
# the public ones; when unset the API is open (local dev + tests).
API_TOKEN = os.environ.get("COACH_API_TOKEN") or None

# Routes reachable without the bearer token. Kept minimal: a health probe for
# the host/load balancer and the deploy script. Everything else is private.
PUBLIC_PATHS = frozenset({"/healthz"})

# /dev/* routes wipe and seed users — destructive. They're enabled by default
# only when the API is unhardened (no token, i.e. local/test). On a real
# deployment (token set) they're off unless explicitly turned back on.
_dev_flag = os.environ.get("COACH_ENABLE_DEV")
DEV_ENABLED = (_dev_flag == "1") if _dev_flag is not None else (API_TOKEN is None)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if API_TOKEN:
        log.info("API auth ENABLED (bearer token). /dev/* %s.",
                 "enabled" if DEV_ENABLED else "disabled")
    else:
        log.warning(
            "API auth DISABLED — no COACH_API_TOKEN set. Fine for local dev, "
            "but set a token before exposing this backend publicly."
        )
    app.state.store = make_store(DB_PATH)
    app.state.llm = LLMClient()
    app.state.calendar = StubCalendarClient()
    app.state.healthkit = StubHealthKitClient()
    app.state.push = make_push(app.state.store)
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


@app.middleware("http")
async def _auth_gate(request: Request, call_next):
    """Single chokepoint for auth + dev-route gating.

    - /dev/* is hidden (404) when DEV_ENABLED is false, so a deployed box never
      exposes the destructive seed/wipe endpoints.
    - When API_TOKEN is set, every path except PUBLIC_PATHS requires a matching
      `Authorization: Bearer <token>`. Compared in constant time. CORS
      preflights (OPTIONS) pass through so browser clients can still negotiate.
    """
    path = request.url.path
    if path.startswith("/dev/") and not DEV_ENABLED:
        return JSONResponse({"detail": "not found"}, status_code=404)
    if API_TOKEN and request.method != "OPTIONS" and path not in PUBLIC_PATHS:
        header = request.headers.get("authorization", "")
        presented = header[7:] if header.startswith("Bearer ") else ""
        if not (presented and hmac.compare_digest(presented, API_TOKEN)):
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
    return await call_next(request)


def _coach_for(user_id: str, domain: str | None = None) -> Coach:
    """
    Instantiate a Coach for a user, picking the persona by:
      1. Explicit `domain` argument (used by intake_submit, which knows the goal
         from the incoming request body before any profile exists).
      2. The user's stored UserProfile.domain (set when intake was recorded).
      3. Default "strength" — gives fresh users a working program even if
         intake hasn't been submitted yet (e.g. for /intake/questions).
    """
    s = app.state
    if domain is None:
        profile = s.store.get_profile(user_id)
        domain = profile.domain if profile else "strength"
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


class ExerciseSwapRequest(BaseModel):
    exercise_name: str          # the exercise the user wants to change
    note: str = ""              # free-form: why, and what they'd prefer (optional)
    # When set, the user picked an explicit replacement from the default
    # equipment-matched alternates the UI showed them. We use it directly and
    # skip the LLM — the decision's already made. `note` is then optional.
    chosen: str | None = None
    apply: bool = True          # mutate the stored program now (vs. preview only)


class ProgramFeedbackRequest(BaseModel):
    note: str                   # free-form feedback about the program as a whole


class TopSetEntry(BaseModel):
    """One per calibration_slot. Reps required; load_lb None for bodyweight."""
    reps: int
    load_lb: float | None = None


class SetLogEntry(BaseModel):
    """Wire shape for one completed set: actual reps + actual load."""
    reps: int
    load_lb: float | None = None


class ExerciseLogEntry(BaseModel):
    """
    Wire shape for one prescribed exercise's outcome.

    `outcome` is per-exercise (done/partial/skipped). `sets` is the per-set
    history (Strong / Hevy style). `actual_*` are the top-set rollup;
    derived server-side from `sets` if the client doesn't send them so the
    calibration logic and per-exercise summaries keep working.
    `calibration_slot` is echoed back from the prescription so the server
    can derive the legacy top_sets dict without re-running the persona.
    """
    outcome: NudgeOutcome
    sets: list[SetLogEntry] = []
    actual_reps: int | None = None
    actual_load_lb: float | None = None
    actual_sets: int | None = None
    note: str | None = None
    calibration_slot: str | None = None


class ReplyBody(BaseModel):
    outcome: NudgeOutcome
    friction: str | None = None
    # Calibration-only structured log. Keyed by lift slot (see
    # ExercisePrescription.calibration_slot). Active-phase logs send {}.
    top_sets: dict[str, TopSetEntry] = {}


class HealthSignalBody(BaseModel):
    kind: str
    value: float
    at: datetime | None = None
    metadata: dict[str, str] = {}


class PushRegister(BaseModel):
    token: str
    platform: str = "ios"


# ---- iPhone signals (Section 8.1) ------------------------------------------

class ReadinessBody(BaseModel):
    """This morning's HealthKit recovery picture. All fields optional — the
    backend scores whatever the user has granted (sleep alone is enough)."""
    sleep_hours: float | None = None
    resting_hr: float | None = None
    hrv_ms: float | None = None
    resting_hr_baseline: float | None = None
    hrv_baseline: float | None = None
    at: datetime | None = None


class PlaceObserveBody(BaseModel):
    """A coordinate observation, posted when a session starts or is logged.
    The brain folds it into the learned training geofence."""
    lat: float
    lon: float


class LocationEventBody(BaseModel):
    """The phone crossed the learned gym geofence."""
    event: str          # "arrived" | "departed"
    lat: float | None = None
    lon: float | None = None


class AutologBody(BaseModel):
    """A HealthKit workout that overlaps the prescribed session window."""
    duration_min: float | None = None
    active_kcal: float | None = None
    avg_hr: float | None = None
    workout_type: str | None = None
    ended_at: datetime | None = None


class VitalSampleBody(BaseModel):
    """One HealthKit reading. `metric` is a canonical coach.vitals key."""
    metric: str
    value: float
    unit: str = ""
    at: datetime | None = None


class VitalsBody(BaseModel):
    """A batch of readings posted by the client (broad ingestion)."""
    samples: list[VitalSampleBody]


class LogSessionBody(BaseModel):
    """
    Per-exercise session log (Section 5: each exercise is the atomic action).

    `exercises` is keyed by the prescribed exercise's name. The server derives
    the session-level outcome from the rollup:
      - all done    → done
      - all skipped → skipped
      - mixed       → partial
    and derives `top_sets` (the calibration payload) from any exercise whose
    `calibration_slot` is set. `friction` remains a session-level free-text
    note for things that aren't pinned to one lift.
    """
    exercises: dict[str, ExerciseLogEntry]
    friction: str | None = None


def _rollup_session_outcome(exercises: dict[str, ExerciseLogEntry]) -> NudgeOutcome:
    """
    Reduce per-exercise outcomes to a single session-level outcome.

    Empty payload defaults to skipped — defensive, this shouldn't happen if
    the iOS sheet enforces "log every prescribed exercise" before sending.
    """
    if not exercises:
        return NudgeOutcome.SKIPPED
    outcomes = {e.outcome for e in exercises.values()}
    if outcomes == {NudgeOutcome.DONE}:
        return NudgeOutcome.DONE
    if outcomes == {NudgeOutcome.SKIPPED}:
        return NudgeOutcome.SKIPPED
    return NudgeOutcome.PARTIAL


def _top_set(sets: list[SetLogEntry]) -> SetLogEntry | None:
    """
    Pick the "top set" from a per-set list — the heaviest load, with reps as
    the tiebreaker (bodyweight lifts use reps alone since load is None).

    This is the same rule a coach uses to estimate 1RM (Epley): the heaviest
    load actually completed is the signal, not the average. Returns None for
    empty input so callers can fall back to whatever the client sent.
    """
    if not sets:
        return None
    def key(s: SetLogEntry) -> tuple[float, int]:
        return (s.load_lb or 0.0, s.reps)
    return max(sets, key=key)


def _rollup_exercise_actuals(entry: ExerciseLogEntry) -> tuple[int | None, float | None]:
    """
    Resolve actual_reps / actual_load_lb for one exercise.

    Prefers an explicit value from the client (lets iOS override if there's
    ever a reason to), falls back to the heaviest set from `sets`.
    """
    if entry.actual_reps is not None or entry.actual_load_lb is not None:
        return entry.actual_reps, entry.actual_load_lb
    top = _top_set(entry.sets)
    if top is None:
        return None, None
    return top.reps, top.load_lb


def _derive_top_sets(exercises: dict[str, ExerciseLogEntry]) -> dict[str, dict[str, float]]:
    """
    Pull calibration top-set data out of the per-exercise log.

    The persona's calibration → active transition reads
    nudge.top_sets[slot] = {reps, load_lb}. We derive it from any logged
    exercise that carries a calibration_slot, using the heaviest set's
    numbers. load_lb omitted → bodyweight.
    """
    out: dict[str, dict[str, float]] = {}
    for log in exercises.values():
        if not log.calibration_slot:
            continue
        reps, load = _rollup_exercise_actuals(log)
        if not reps:
            continue
        entry: dict[str, float] = {"reps": float(reps)}
        if load is not None:
            entry["load_lb"] = load
        out[log.calibration_slot] = entry
    return out


# ---- routes ----------------------------------------------------------------

@app.get("/healthz")
def healthz() -> dict[str, Any]:
    # Surface whether the LLM is real or stubbed AND which provider —
    # lets the caller (and the deploy script) see at a glance whether
    # nudges and coach replies are canned or genuinely Claude/GPT-authored.
    llm: LLMClient = app.state.llm
    return {
        "status": "ok",
        "llm_mode": "real" if llm._client is not None else "stub",
        "llm_provider": llm.provider_name,
        "llm_model": llm.model,
    }


@app.get("/intake/questions")
def intake_questions(x_user_id: str = Header(default=None)) -> dict[str, Any]:
    coach = _coach_for(_uid(x_user_id))
    qs = coach.intake_questions()
    return {"questions": [{"key": q.key, "q": q.q} for q in qs]}


@app.post("/intake/submit", response_model=IntakeResponse)
def intake_submit(body: IntakeSubmit, x_user_id: str = Header(default=None)) -> IntakeResponse:
    # Pick the persona BEFORE record_intake based on the goal in the answers.
    # Otherwise we'd build the user's program with the wrong template.
    from coach.personas import goal_to_domain
    domain = goal_to_domain(body.answers.get("goal"))
    coach = _coach_for(_uid(x_user_id), domain=domain)
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


@app.get("/notifications/plan")
def notifications_plan(hour: int = 17, x_user_id: str = Header(default=None)) -> dict[str, Any]:
    """Weekly local-notification plan for the iOS client to schedule on-device.

    Free alternative to APNs push (which needs a paid Apple account): the app
    turns these into repeating local calendar notifications. Derived from the
    user's training cadence; see coach/reminders.py. `hour` is the assumed
    local training time (the client may later let the user set it).
    """
    from coach.reminders import weekly_reminder_plan, plan_as_dicts

    user_id = _uid(x_user_id)
    profile = app.state.store.get_profile(user_id)
    days_per_week = 3
    if profile and profile.derived:
        days_per_week = int(profile.derived.get("days_per_week", 3) or 3)
    ident = app.state.store.get_identity_for_user(user_id)
    plan = weekly_reminder_plan(
        days_per_week=days_per_week,
        identity_statement=ident.statement if ident else None,
        hour=hour,
    )
    return {"reminders": plan_as_dicts(plan)}


@app.post("/nudge/{nudge_id}/reply")
def reply(nudge_id: str, body: ReplyBody, x_user_id: str = Header(default=None)) -> dict[str, Any]:
    coach = _coach_for(_uid(x_user_id))
    top_sets_dict = {k: v.model_dump() for k, v in body.top_sets.items()}
    nudge, ripples, handoff = coach.record_report(
        nudge_id, body.outcome, body.friction, top_sets=top_sets_dict
    )
    rationale = coach.adapt()
    # The coach's spoken reply — separate from the rationale (which is the
    # programming change). This is what makes a tap feel like a conversation.
    action = app.state.store.get_action(nudge.action_id)
    coach_response = coach.compose_coach_response(
        body.outcome, body.friction, action.title if action else None
    )
    return {
        "ok": True,
        "ripples": ripples,
        "handoff": handoff,
        "adaptation": rationale,
        "outcome": nudge.outcome.value,
        "coach_response": coach_response,
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


# ---- iPhone signals (Section 8.1) ------------------------------------------

@app.post("/signals/readiness")
def signals_readiness(body: ReadinessBody, x_user_id: str = Header(default=None)) -> dict[str, Any]:
    """Feature 1 — Readiness Engine.

    The iOS client posts this morning's HealthKit recovery signals (sleep,
    resting HR, HRV + the user's own trailing baselines). We score them
    deterministically, persist the snapshot, and hand back the score, band,
    the directive that /session/next will apply, and a coach-voiced line.
    """
    coach = _coach_for(_uid(x_user_id))
    snap = coach.record_readiness(
        sleep_hours=body.sleep_hours,
        resting_hr=body.resting_hr,
        hrv_ms=body.hrv_ms,
        resting_hr_baseline=body.resting_hr_baseline,
        hrv_baseline=body.hrv_baseline,
        at=body.at,
    )
    _, directive = coach.readiness_directive()
    return {
        "ok": True,
        "score": snap.score,
        "band": snap.band,
        "directive": directive,
        "note": coach.readiness_note(snap),
    }


@app.post("/signals/place/observe")
def signals_place_observe(body: PlaceObserveBody, x_user_id: str = Header(default=None)) -> dict[str, Any]:
    """Feature 2 — learn where the user trains.

    Posted when a session starts or is logged. The brain folds the coordinate
    into a running centroid; once `monitorable` is true the client starts
    region-monitoring the returned geofence.
    """
    coach = _coach_for(_uid(x_user_id))
    place = coach.observe_training_place(body.lat, body.lon)
    return {
        "ok": True,
        "lat": place.lat,
        "lon": place.lon,
        "radius_m": place.radius_m,
        "label": place.label,
        "confidence": place.confidence,
        "monitorable": place.monitorable,
    }


@app.get("/signals/place")
def signals_place(x_user_id: str = Header(default=None)) -> dict[str, Any]:
    """The learned training geofence, or monitorable=False if none yet."""
    coach = _coach_for(_uid(x_user_id))
    place = coach.learned_place()
    if place is None:
        return {"monitorable": False}
    return {
        "lat": place.lat,
        "lon": place.lon,
        "radius_m": place.radius_m,
        "label": place.label,
        "confidence": place.confidence,
        "monitorable": place.monitorable,
    }


@app.post("/signals/location-event")
def signals_location_event(body: LocationEventBody, x_user_id: str = Header(default=None)) -> dict[str, Any]:
    """The phone crossed the gym geofence — arrived or departed."""
    coach = _coach_for(_uid(x_user_id))
    return {"ok": True, **coach.record_location_event(body.event, body.lat, body.lon)}


@app.post("/signals/vitals")
def signals_vitals(body: VitalsBody, x_user_id: str = Header(default=None)) -> dict[str, Any]:
    """Broad HealthKit ingestion — store a batch of metric readings.

    The client posts everything Health grants (body weight, sleep, steps, …);
    we keep a rolling per-metric time series the coach reads for trends. Unknown
    metric keys are dropped server-side. Idempotent on (metric, timestamp).
    """
    from coach.models import VitalSample
    coach = _coach_for(_uid(x_user_id))
    samples = [
        VitalSample(metric=s.metric, value=s.value, unit=s.unit,
                    at=s.at or datetime.now(timezone.utc))
        for s in body.samples
    ]
    stored = coach.record_vitals(samples)
    return {"ok": True, "stored": stored}


@app.get("/vitals/summary")
def vitals_summary(x_user_id: str = Header(default=None)) -> dict[str, Any]:
    """Per-metric trend summary + cross-metric insights (weight trajectory,
    relative strength). Powers the Vitals dashboard."""
    coach = _coach_for(_uid(x_user_id))
    return coach.vitals_summary()


@app.get("/vitals/series")
def vitals_series(metric: str, days: int = 90, x_user_id: str = Header(default=None)) -> dict[str, Any]:
    """Raw points for one metric over the last `days` — for charting."""
    from coach.vitals import spec_for
    user_id = _uid(x_user_id)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    series = app.state.store.vitals_series(user_id, metric, since=since)
    spec = spec_for(metric)
    return {
        "metric": metric,
        "label": spec.label if spec else metric,
        "unit": spec.unit if spec else "",
        "points": [{"at": s.at.isoformat(), "value": s.value} for s in series],
    }


@app.post("/session/{action_id}/autolog")
def session_autolog(action_id: str, body: AutologBody, x_user_id: str = Header(default=None)) -> dict[str, Any]:
    """Feature 3 — auto-log a session from an Apple Health workout.

    Logs the prescribed session DONE via a SENSOR verification (the strongest
    kind), enriched with the real duration / calories / heart rate, then adapts
    the program and composes the coach's spoken reply — same downstream effect
    as a manual log, but the user never typed anything.
    """
    coach = _coach_for(_uid(x_user_id))
    try:
        nudge, ripples = coach.autolog_from_workout(
            action_id,
            duration_min=body.duration_min,
            active_kcal=body.active_kcal,
            avg_hr=body.avg_hr,
            workout_type=body.workout_type,
            ended_at=body.ended_at,
        )
    except ValueError as e:
        raise HTTPException(404, str(e))
    rationale = coach.adapt()
    action = app.state.store.get_action(action_id)
    coach_response = coach.compose_coach_response(
        NudgeOutcome.DONE, nudge.friction_note, action.title if action else None
    )
    return {
        "ok": True,
        "ripples": ripples,
        "adaptation": rationale,
        "outcome": nudge.outcome.value,
        "coach_response": coach_response,
    }


@app.post("/ai_program/build")
def ai_program_build(x_user_id: str = Header(default=None)) -> dict[str, Any]:
    """
    Build an LLM-generated weekly program for this user and persist it.

    Reads the user's existing profile (intake must already be submitted).
    Calls the split planner + per-day exercise picker, validates the output,
    saves it, and flips profile.derived["use_ai_program"]=true so that
    subsequent /session/next calls render from the AIProgram instead of the
    hardcoded persona template.

    Returns the generated program — clients can render it as a "this is what
    your AI coach planned" preview.

    Idempotent: re-call to regenerate (e.g. after the user reports an
    injury that changes equipment / constraints).
    """
    from coach.ai_program import build_program

    user_id = _uid(x_user_id)
    profile = app.state.store.get_profile(user_id)
    if profile is None:
        raise HTTPException(409, "no profile yet — submit /intake/submit first")

    # Carry forward everything the user has told us — standing constraints
    # injected into the prompts, avoided exercises filtered + hard-rejected.
    adjustments = app.state.store.get_adjustments(user_id)
    constraints = [a.constraint for a in adjustments.active_constraints()]
    avoided = adjustments.avoided_exercises()

    program = build_program(
        profile, app.state.llm, constraints=constraints, avoided=avoided,
    )
    app.state.store.save_ai_program(user_id, program)

    # Persist the opt-in flag so /session/next reads from the AIProgram next
    # time. We set it AFTER the save so a failed build doesn't strand the
    # user with a flag but no program.
    profile.derived["use_ai_program"] = True
    app.state.store.save_profile(profile)

    return {
        "ok": True,
        "days_built": len(program.days),
        "issues": [i.model_dump() for i in program.issues],
        "program": program.model_dump(),
    }


@app.post("/exercise/swap")
def exercise_swap(body: ExerciseSwapRequest, x_user_id: str = Header(default=None)) -> dict[str, Any]:
    """
    Swap an exercise the user can't or won't do, with a free-form reason.

    This is the "real coach listens and remembers" path. The user writes WHY
    in their own words ("squats wreck my knee, give me something gentler"); the
    LLM reads it against equipment-matched catalog alternatives, picks the best
    replacement, and — critically — records a STANDING CONSTRAINT so the
    vetoed exercise never silently returns on the next program build.

    When apply=true and the user has a stored AIProgram, we also patch the
    replacement into the live program immediately so the change is visible
    before any rebuild.
    """
    from coach.adjust import direct_exercise_swap, interpret_exercise_swap
    from coach.exercises import catalog as _catalog

    user_id = _uid(x_user_id)
    profile = app.state.store.get_profile(user_id)
    if profile is None:
        raise HTTPException(409, "no profile yet — submit /intake/submit first")

    cat = _catalog()
    original = cat.get(body.exercise_name)
    if original is None:
        raise HTTPException(404, f"No exercise named {body.exercise_name!r} in catalog.")

    if body.chosen:
        # User picked an explicit replacement from the default alternates —
        # use it directly, no LLM. Validate it's a real catalog exercise.
        chosen_ex = cat.get(body.chosen)
        if chosen_ex is None:
            raise HTTPException(404, f"No exercise named {body.chosen!r} in catalog.")
        result, adjustment = direct_exercise_swap(
            user_id=user_id, exercise=original, chosen=chosen_ex.name, note=body.note or None,
        )
    else:
        available = cat.equipment_for_profile(profile.answers.get("equipment"))
        candidates = cat.alternates_for(original, available, limit=8)
        result, adjustment = interpret_exercise_swap(
            user_id=user_id,
            exercise=original,
            note=body.note,
            candidates=candidates,
            profile=profile,
            llm=app.state.llm,
        )

    # Record the decision in coach memory — this is what makes it stick.
    log = app.state.store.get_adjustments(user_id)
    log.append(adjustment)
    app.state.store.save_adjustments(log)

    # Patch the live program now so the swap is immediately visible.
    patched = False
    if body.apply and result.replacement:
        ai_program = app.state.store.get_ai_program(user_id)
        if ai_program is not None:
            for day in ai_program.days:
                for pick in day.exercises:
                    if pick.catalog_name.lower() == body.exercise_name.lower():
                        pick.catalog_name = result.replacement
                        pick.rationale = result.coach_response
                        patched = True
            if patched:
                app.state.store.save_ai_program(user_id, ai_program)

    # Narrative memory — the journal sees the swap too.
    coach = _coach_for(user_id)
    coach.journal.append(user_id, kind="adjust", event={
        "scope": "exercise",
        "from": body.exercise_name,
        "to": result.replacement,
        "note": body.note,
    })

    return {
        "ok": True,
        "replacement": result.replacement,
        "alternatives": result.alternatives,
        "coach_response": result.coach_response,
        "constraint": result.constraint,
        "applied": patched,
    }


@app.post("/program/feedback")
def program_feedback(body: ProgramFeedbackRequest, x_user_id: str = Header(default=None)) -> dict[str, Any]:
    """
    Take free-form feedback about the program as a whole and act on it.

    "I'm wiped after these" / "I can only do 3 days now" / "more upper body".
    The LLM interprets the complaint into a concrete directive, records it as
    a standing constraint, and — when the feedback changes the program's shape
    — regenerates the program carrying every prior constraint forward.
    """
    from coach.adjust import interpret_program_feedback
    from coach.ai_program import build_program

    user_id = _uid(x_user_id)
    profile = app.state.store.get_profile(user_id)
    if profile is None:
        raise HTTPException(409, "no profile yet — submit /intake/submit first")

    log = app.state.store.get_adjustments(user_id)
    prior = [a.constraint for a in log.active_constraints()]

    # Summarize the current program for the interpreter (day names + counts).
    ai_program = app.state.store.get_ai_program(user_id)
    if ai_program is not None:
        program_summary = "; ".join(
            f"Day {d.spec.day_index} ({d.spec.kind}): {d.spec.name} — "
            f"{len(d.exercises)} exercises"
            for d in ai_program.days
        )
    else:
        program_summary = "(no AI program built yet)"

    result, adjustment = interpret_program_feedback(
        user_id=user_id,
        note=body.note,
        program_summary=program_summary,
        profile=profile,
        prior_constraints=prior,
        llm=app.state.llm,
    )

    log.append(adjustment)
    app.state.store.save_adjustments(log)

    regenerated = False
    if result.regenerate:
        constraints = [a.constraint for a in log.active_constraints()]
        avoided = log.avoided_exercises()
        program = build_program(
            profile, app.state.llm, constraints=constraints, avoided=avoided,
        )
        app.state.store.save_ai_program(user_id, program)
        regenerated = True

    coach = _coach_for(user_id)
    coach.journal.append(user_id, kind="adjust", event={
        "scope": "program",
        "note": body.note,
        "change": result.change_summary,
    })

    return {
        "ok": True,
        "coach_response": result.coach_response,
        "change_summary": result.change_summary,
        "constraint": result.constraint,
        "regenerated": regenerated,
    }


@app.get("/adjustments")
def get_adjustments(x_user_id: str = Header(default=None)) -> dict[str, Any]:
    """The coach's memory of every change this user has requested."""
    log = app.state.store.get_adjustments(_uid(x_user_id))
    return {"adjustments": [a.model_dump() for a in log.adjustments]}


@app.get("/session/next")
def session_next(x_user_id: str = Header(default=None)) -> dict[str, Any]:
    """
    The next prescribed session — what the coach would push if it were the moment.

    Minting via `prepare_next_action` so a real AtomicAction id exists in the
    store; iOS then references that id when logging or scheduling. This is the
    same code path the nudge engine uses, so what the user sees is what would
    have been pushed.
    """
    from coach.personas import domain_is_implemented_for_goal, goal_to_domain

    user_id = _uid(x_user_id)
    coach = _coach_for(user_id)
    try:
        action, session = coach.prepare_next_action()
    except RuntimeError as e:
        raise HTTPException(409, str(e))

    # Surface whether the user's requested goal is using a real template
    # or has been routed to the strength fallback. iOS uses this to render a
    # "your [X] template is coming soon" banner on the Now tab.
    profile = app.state.store.get_profile(user_id)
    requested_goal = (profile.answers.get("goal") if profile else None) or "get_stronger"
    is_fallback = (
        goal_to_domain(requested_goal) == "strength"
        and not domain_is_implemented_for_goal(requested_goal)
    )

    # Calibration metadata — iOS uses these to render a "Week 1 calibration"
    # banner, a 1/5..5/5 progress indicator, and (for active phase) the
    # benchmark summary on the Becoming tab. Older clients ignore the
    # field; default phase="active" keeps non-migrated personas behaving.
    program = app.state.store.get_program(user_id)
    phase = program.phase if program else "active"
    calibration_index = program.calibration_index if program else 0
    # Per-persona; 0 for personas that haven't migrated to calibration-first
    # (in which case phase stays "active" and the banner stays hidden).
    calibration_length = coach.persona.calibration_length

    # AI program override — when the user has opted in AND has a saved
    # AIProgram AND we're past calibration, replace the persona's hardcoded
    # exercise list with the LLM-picked one. Everything else (scheduling,
    # action id, calibration metadata, summary/progression rule) stays as
    # the persona built it. The persona still owns numbers; the LLM only
    # owns exercise selection.
    if (
        phase == "active"
        and profile is not None
        and profile.derived.get("use_ai_program")
    ):
        ai_program = app.state.store.get_ai_program(user_id)
        if ai_program is not None and ai_program.days:
            from coach.ai_program import render_session_from_ai_program
            session_idx = program.session_index if program else 0
            session = render_session_from_ai_program(
                ai_program=ai_program,
                session_index=session_idx,
                goal_domain=coach.persona.domain,
                progression=(program.progression if program else {}),
                fallback=session,
            )

    # Readiness Engine (Feature 1) — if the user posted this morning's recovery
    # signals, surface the score + the directive the coach is applying to today
    # (full / reduced / rest) + a coach-voiced line. Absent → client hides the
    # banner and trains as planned.
    readiness_snap, readiness_directive = coach.readiness_directive()
    readiness_block = None
    if readiness_snap is not None and readiness_snap.band != "unknown":
        readiness_block = {
            "score": readiness_snap.score,
            "band": readiness_snap.band,
            "directive": readiness_directive,
            "note": coach.readiness_note(readiness_snap),
            "sleep_hours": readiness_snap.sleep_hours,
            "resting_hr": readiness_snap.resting_hr,
            "hrv_ms": readiness_snap.hrv_ms,
        }

    return {
        "action_id": action.id,
        "action_title": action.title,
        "prescribed_for": action.prescribed_for.isoformat() if action.prescribed_for else None,
        "expected_minutes": session.expected_minutes,
        "cue": action.cue,
        "location": action.location,
        "minimum_dose": action.minimum_dose,
        "goal": requested_goal,
        "is_fallback": is_fallback,
        "readiness": readiness_block,
        "phase": phase,
        "calibration_index": calibration_index,
        "calibration_length": calibration_length,
        "calibration_results": (program.calibration_results if program else {}),
        "emphasis_slot": (program.emphasis_slot if program else None),
        "session": {
            "name": session.name,
            "summary": session.summary,
            "expected_minutes": session.expected_minutes,
            "progression_rule": session.progression_rule,
            "exercises": [e.model_dump() for e in session.exercises],
        },
    }


@app.get("/coach/today")
def coach_today(x_user_id: str = Header(default=None)) -> dict[str, Any]:
    """The single shape the v2 Coach tab renders right now — Quiet / Prescription
    / Slip / Return / Pause — with the Marcus-voiced line + the data its CTAs
    need. See design/v2/screens/01-coach-tab.md."""
    coach = _coach_for(_uid(x_user_id))
    return coach.coach_today()


class PauseBody(BaseModel):
    days: int = 7


@app.post("/program/pause")
def program_pause(body: PauseBody, x_user_id: str = Header(default=None)) -> dict[str, Any]:
    """Pause the program for N days (Shape D 'give me a week' / Settings)."""
    coach = _coach_for(_uid(x_user_id))
    try:
        until = coach.pause_program(body.days)
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return {"ok": True, "paused_until": until.isoformat()}


@app.post("/program/resume")
def program_resume(x_user_id: str = Header(default=None)) -> dict[str, Any]:
    coach = _coach_for(_uid(x_user_id))
    coach.resume_program()
    return {"ok": True}


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
        # The coach's most recent surface-worthy observation. This is the
        # "From your coach" card on Today — the moment that makes the app
        # feel like it sees the user (Principle 2.3). May be None.
        "latest_observation": _journal_entry_payload(
            coach.journal.latest_surfaced(user_id)
        ),
        # The most recent journal entry of any kind — useful for debug pane.
        "latest_journal_entry": _journal_entry_payload(
            (store.get_journal(user_id).entries[-1]
             if store.get_journal(user_id) and store.get_journal(user_id).entries
             else None)
        ),
    }


def _journal_entry_payload(entry) -> dict[str, Any] | None:
    if entry is None:
        return None
    return {
        "id": entry.id,
        "at": entry.at.isoformat(),
        "kind": entry.kind,
        "text": entry.text,
        "surface": entry.surface,
        "reason_for_surface": entry.reason_for_surface,
    }


@app.get("/dev/scenarios")
def dev_scenarios_list() -> dict[str, Any]:
    """Surface the catalog of seedable scenarios + selectable goals so the iOS
    Dev sheet can render its pickers without hardcoding names client-side."""
    from coach.dev_scenarios import scenarios_list, GOALS_LIST
    return {"scenarios": scenarios_list(), "goals": GOALS_LIST}


class SeedScenarioBody(BaseModel):
    goal: str
    scenario: str
    identity: str = "I am someone who shows up."


@app.post("/dev/seed")
def dev_seed(body: SeedScenarioBody, x_user_id: str = Header(default=None)) -> dict[str, Any]:
    """
    Dev-only: wipe the user and apply a canned scenario. Lets you iterate
    on flows (calibration banner, Summit hero at different vote counts,
    streak-broken state) without manually clicking through onboarding.

    Bypasses LLM-driven profile derivation and mirror-integrity on world
    state. Production paths never call this.
    """
    from coach.dev_scenarios import apply_scenario
    try:
        summary = apply_scenario(
            app.state.store, _uid(x_user_id), body.goal, body.scenario,
            identity_statement=body.identity,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, **summary}


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
    from coach.models import ExerciseLog
    coach = _coach_for(_uid(x_user_id))
    rollup_outcome = _rollup_session_outcome(body.exercises)
    top_sets_dict = _derive_top_sets(body.exercises)
    # Round-trip through ExerciseLog so the Nudge model gets typed instances
    # rather than raw dicts (the field is `dict[str, ExerciseLog]`).
    # When the client sent per-set data but no top-line rollup, backfill it
    # here so downstream consumers (calibration, summaries) see a flat
    # actual_reps/actual_load_lb in addition to the granular `sets` array.
    exercise_logs: dict[str, ExerciseLog] = {}
    for name, entry in body.exercises.items():
        reps, load = _rollup_exercise_actuals(entry)
        payload = entry.model_dump()
        payload["actual_reps"] = reps
        payload["actual_load_lb"] = load
        exercise_logs[name] = ExerciseLog(**payload)
    try:
        nudge, ripples, handoff = coach.log_session(
            action_id,
            rollup_outcome,
            body.friction,
            top_sets=top_sets_dict,
            exercise_logs=exercise_logs,
        )
    except ValueError as e:
        raise HTTPException(404, str(e))
    rationale = coach.adapt()
    action = app.state.store.get_action(action_id)
    coach_response = coach.compose_coach_response(
        rollup_outcome, body.friction, action.title if action else None
    )
    return {
        "ok": True,
        "ripples": ripples,
        "handoff": handoff,
        "adaptation": rationale,
        "outcome": nudge.outcome.value,
        "coach_response": coach_response,
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


# Free-exercise-db ships demonstration images via GitHub's raw CDN. We vendor
# only the JSON metadata in backend/data/exercises.json; the image bytes stay
# on GitHub. Keeps the repo lean and lets clients cache via the standard URL
# cache. The dataset path layout is `<repo>/exercises/<slug>/0.jpg` etc.
_EXERCISE_IMAGE_BASE = (
    "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/exercises/"
)


@app.get("/exercise")
def exercise_detail(name: str) -> dict[str, Any]:
    """
    Look up one exercise by exact (case-insensitive) name and return everything
    needed to render a demonstration: stepwise instructions, primary/secondary
    muscles, equipment, level, mechanic, and absolute image URLs.

    Public — exercise reference data isn't user-specific, so no auth needed.
    iOS opens this on a row tap to populate the detail sheet.
    """
    from coach.exercises import catalog as _catalog
    ex = _catalog().get(name)
    if ex is None:
        raise HTTPException(404, f"No exercise named {name!r} in catalog.")
    return {
        "name": ex.name,
        "instructions": ex.instructions,
        "primary_muscles": ex.primary_muscles,
        "secondary_muscles": ex.secondary_muscles,
        "equipment": ex.equipment,
        "level": ex.level,
        "mechanic": ex.mechanic,
        "category": ex.category,
        "image_urls": [_EXERCISE_IMAGE_BASE + p for p in ex.images],
    }


@app.get("/exercises/alternates")
def exercise_alternates(
    name: str,
    x_user_id: str = Header(default=None),
) -> dict[str, Any]:
    """
    Return up to 3 alternate exercises for the user to swap in.

    Same primary muscle, same movement pattern (mechanic), same category,
    filtered by the user's equipment. Excludes the original.

    Per design feedback: "give me 3 truly viable alternatives, not redundant —
    don't swap upper chest with lower chest because they're different parts."
    The alternates_for() catalog method enforces those rules.
    """
    from coach.exercises import catalog as _catalog
    user_id = _uid(x_user_id)
    cat = _catalog()
    original = cat.get(name)
    if original is None:
        raise HTTPException(404, f"No exercise named {name!r} in catalog.")

    profile = app.state.store.get_profile(user_id)
    eq_answer = profile.answers.get("equipment") if profile else None
    available = cat.equipment_for_profile(eq_answer)

    alternates = cat.alternates_for(original, available, limit=3)
    return {
        "original": original.name,
        "alternates": [
            {
                "name": a.name,
                "primary_muscles": a.primary_muscles,
                "equipment": a.equipment,
                "level": a.level,
                "first_instruction": a.first_instruction(),
            }
            for a in alternates
        ],
    }
