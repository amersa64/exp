"""
End-to-end CLI demonstration of the coaching loop.

Run:  python -m cli.demo

This is the simulator from Section 13 step 2 — "Coaching lifecycle, text-only".
It instantiates a coach, runs INTAKE → PROGRAM → PROMPT → EXECUTE → REPORT →
ADAPT for two weeks of simulated time, prints what the brain decided at every
step, and ends with the World state (which must have grown ONLY from verified
events — try editing the code to grow it any other way and the store will
reject it; that's the mirror principle made literal).

If ANTHROPIC_API_KEY is set, real Sonnet output is used. Otherwise the stub LLM
keeps everything runnable offline.
"""

from __future__ import annotations

import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

# Allow running from repo root without install.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from coach.integrations import (
    CalendarEvent,
    HealthSignal,
    StubCalendarClient,
    StubHealthKitClient,
)
from coach.lifecycle import Coach
from coach.llm import LLMClient
from coach.models import NudgeOutcome
from coach.store import Store


def _line(title: str) -> None:
    print("\n" + "─" * 4, title, "─" * (74 - len(title)))


def _utc(y, m, d, h=9, mn=0) -> datetime:
    return datetime(y, m, d, h, mn, tzinfo=timezone.utc)


def main() -> int:
    store = Store(":memory:")
    llm = LLMClient()
    cal = StubCalendarClient()
    hk = StubHealthKitClient()

    user_id = "demo-user"
    coach = Coach(user_id, "fitness", store, llm, cal, hk)

    if llm._client is None:
        print("[i] No ANTHROPIC_API_KEY — running with stub LLM. Real Sonnet text appears when the key is set.\n")

    # ---- STAGE 1: INTAKE ----------------------------------------------------
    _line("STAGE 1 — INTAKE (assessment before prescription, Rubric B1)")
    questions = coach.intake_questions()
    for q in questions:
        print(f"  Q ({q.key}): {q.q}")
    answers = {
        "experience": "novice — been to a gym, never on a real program",
        "days_per_week": "3",
        "injuries": "none",
        "equipment": "barbell + rack at home, no DBs",
        "baseline_squat": "135",
    }
    profile, handoff = coach.record_intake(answers)
    if handoff:
        print("  SAFETY HANDOFF:", handoff)
        return 0
    print("\n  Derived profile:")
    for k, v in profile.derived.items():
        print(f"    {k} = {v}")

    # ---- STAGE 2: PROGRAM ---------------------------------------------------
    _line("STAGE 2 — PROGRAM (specific lifts/sets/reps, Rubric B2/B4)")
    identity, milestones, habits, program = coach.build_program(
        "I am the kind of person who trains 3 times a week — strong, energetic, durable."
    )
    print(f"  Identity: {identity.statement}")
    print(f"  Program: {program.program_name}")
    print(f"  Starting loads: squat={program.progression['squat_lb']}lb, "
          f"bench={program.progression['bench_lb']}lb, "
          f"deadlift={program.progression['deadlift_lb']}lb")
    print(f"  Milestones: " + " · ".join(m.title for m in milestones))
    print(f"  Habits   : " + " · ".join(f"{h.title} ({h.cadence})" for h in habits))

    # Seed a realistic calendar for the demo: a few meetings each "day".
    today = _utc(2026, 5, 25, 9)
    cal.seed(user_id, [
        CalendarEvent("m1", "Standup", today.replace(hour=10), today.replace(hour=10, minute=30)),
        CalendarEvent("m2", "1:1",     today.replace(hour=14), today.replace(hour=15)),
    ])

    # ---- STAGE 3 + 4: PROMPT + EXECUTE -------------------------------------
    _line("STAGE 3+4 — PROMPT (fire nudge) + EXECUTE (block calendar)")
    nudge = coach.try_nudge(now=today)
    if nudge is None:
        print("  Engine chose silence — that is a valid output (Rubric D3).")
        return 0
    action = store.get_action(nudge.action_id)
    print(f"  → NUDGE fired at {nudge.fired_at:%Y-%m-%d %H:%M} UTC")
    print(f"    reason: {nudge.fired_because}")
    print(f"    body  : {nudge.body}")
    print(f"    II    : {nudge.implementation_intention}")
    exec_result = coach.execute_in_calendar(action, now=today)
    print(f"  → CALENDAR: {exec_result}")

    # ---- STAGE 5: REPORT (loop closure, Rubric A4) -------------------------
    _line("STAGE 5 — REPORT (one-tap reply, world grows ONLY from this)")
    _, ripples, _ = coach.record_report(nudge.id, NudgeOutcome.DONE,
                                         friction_note="felt about right, last set was a grind")
    print(f"  User tapped: done. World ripples ↑ {' · '.join(ripples)}")
    world = store.get_world(user_id)
    print(f"  World now: currency={world.currency}, streak={world.streak_days}, "
          f"theme={world.theme}, living_systems={ {k: round(v,2) for k,v in world.living_systems.items()} }")

    # ---- STAGE 6: ADAPT (the differentiator from a plan generator) ---------
    _line("STAGE 6 — ADAPT (Rubric B3 — coach, not plan generator)")
    rationale = coach.adapt()
    print(f"  Coach's decision: {rationale}")
    program = store.get_program(user_id)
    print(f"  Next-session loads: squat={program.progression['squat_lb']}lb, "
          f"bench={program.progression['bench_lb']}lb, "
          f"deadlift={program.progression['deadlift_lb']}lb, "
          f"ohp={program.progression['ohp_lb']}lb")

    # ---- Day 2: nudge ignored → engine should back off ---------------------
    _line("DAY 2 — user ignores. Engine demonstrates restraint (Rubric D3)")
    day2 = today + timedelta(days=1)
    cal.seed(user_id, [
        CalendarEvent("m3", "Deep work", day2.replace(hour=10), day2.replace(hour=12)),
    ])
    n2 = coach.try_nudge(now=day2)
    if n2:
        print(f"  Nudge fired: {n2.body}")
        # Simulate user ignoring it: fast-forward past the window
        coach.nudge_engine.sweep_ignored(user_id, day2 + timedelta(hours=3))
        followups = coach.open_followups(now=day2 + timedelta(hours=3))
        for f in followups:
            print(f"  FOLLOWUP: {f.prompt}")

    # ---- Day 3: sensor verification grows the world honestly ---------------
    _line("DAY 3 — HealthKit reports a workout; world grows from a SENSOR signal")
    day3 = today + timedelta(days=2)
    hk.seed(HealthSignal(user_id, "workout", day3.replace(hour=18), 45.0,
                         {"type": "strength_training"}))
    action3, _ = coach.prepare_next_action()
    ripples3 = coach.record_sensor_verification(action3.id, "healthkit.workout",
                                                 {"duration_min": 45})
    print(f"  Sensor-verified. World ripples ↑ {' · '.join(ripples3)}")

    # ---- Mirror-integrity proof (Rubric E3) --------------------------------
    _line("MIRROR INTEGRITY CHECK (Rubric E3 — the cardinal principle)")
    world = store.get_world(user_id)
    world.currency += 9999  # someone tries to grow the world without verification
    try:
        store.save_world(world)  # no growth_event → must be rejected
    except PermissionError as e:
        print(f"  ✓ Store rejected illegal mutation: {e}")
    else:
        print("  ✗ FAIL — the world was mutated without a verified event. BUG.")
        return 1

    _line("END — full lifecycle demonstrated")
    print("  All six stages of Section 4.1 exercised.")
    print(f"  Final world: currency={store.get_world(user_id).currency}, "
          f"streak={store.get_world(user_id).streak_days}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
