# Handoff — continue development locally

You're picking up from a remote session that built the backend brain + iOS scaffold for The Coach (see `spec.md`, the contract). This doc is a 5-minute briefing. Read `spec.md` (especially Sections 1, 2, 11, 12) and `README.md` (the rubric scorecard) before touching code.

## First thing: verify the build still works

```bash
pip install -e ".[dev]"
python -m pytest backend          # expect: 21 passed
python -m cli.demo                # walks the full lifecycle in <1s
```

If those don't pass, fix that before adding anything.

## What's done (don't redo these)

- Four-level data model (Section 5) with the **mirror principle** enforced in code — `WorldState.grow()` and `Store.save_world()` both refuse to mutate without a `VerifiedEvent`. There is intentionally no `POST /world` endpoint. **Do not break this.** It's the cardinal principle (2.6 / E3).
- Section 4.1 lifecycle end-to-end: intake → program → prompt → execute → report → adapt → loop-closing (`coach/lifecycle.py`).
- Autonomous scheduler (`coach/scheduler.py`) — the brain wakes itself; daily cap + cooldown + back-off all live in `coach/nudge.py`.
- Structural variety guard (`coach/variety.py`) — Jaccard + opening-word check; nudges that look templated are silently dropped.
- FastAPI HTTP layer (`api/app.py`) — the iOS client's backend.
- Fitness persona (`coach/personas/fitness.py`) — real novice linear progression that progresses on success and deloads after two partials. **This is the only domain in v1. Do not add a second.**
- Safety boundary (`coach/safety.py`) — handoff messages for injury/medical/mental-health signals.
- Anthropic SDK wired with a stub fallback (`coach/llm.py`) — set `ANTHROPIC_API_KEY` for real LLM-authored nudges.
- 21 tests, each mapped to a rubric item in Section 12.

## What's next, in priority order

Each task is sized for one focused session. Verify with `python -m pytest backend` after each.

1. **Get the iOS app building in Xcode.** Files are in `ios/TheCoach/`; SwiftPM or a fresh iOS App target both work. Smoke test: launch in the simulator while the backend is running locally, complete IntakeView, then `curl -X POST http://127.0.0.1:8765/scheduler/tick` and watch the WorldView refresh. Expect signing/capability errors — that's normal for a new project. Don't redesign UI yet; just get it on screen.

2. **Real Google Calendar adapter** (replace `integrations/calendar.py`'s `StubCalendarClient`). OAuth2 device flow or installed-app flow; persist tokens server-side. Keep the `CalendarClient` Protocol unchanged so nothing else needs to move. Closes F1/F2 (currently scored 1).

3. **Real APNs push delivery** (`coach/push.py` has the scaffolded `APNsPushDelivery`). HTTP/2 to `api.push.apple.com` with a JWT signed by your .p8 key. Closes the last gap on A2/A3.

4. **HealthKit read on the iOS side** (`ios/.../HealthKitService.swift`) — observe workouts and POST to `/healthkit/signal`. The backend already verifies workouts against the latest prescribed action and grows the world if matched. Closes F3.

5. **The growing world visuals** (Section 13 step 6, Rubric E1/E2 — currently 1). This is the only "make it pretty" task and the spec says to do it last for a reason. Start with the four-zoom WorldView; render `living_systems[habit_id]` as something that visibly thrives or wilts. Stay obsessive about Section 6.3: the world is read-only reflection, never where work happens.

6. **Tune nudge timing with richer M+A signal.** Right now `decide_timing` uses calendar gaps + a "signals" summary string. Wire real heuristics: low recent steps → suggest movement now; recent high exertion → shrink the ask (2-minute rule, Section 3.4); fired-after-not-now → extra cooldown. Closes D1.

## Hard rules — re-read Section 11 before each session

- **Do not** add a "log your workout" form, a habit-grid dashboard, or any UI where the user maintains state. The user reports outcomes via one-tap reply only. (Violates Push-not-pull.)
- **Do not** add a code path that grows the world from in-app action. (Violates the mirror principle. Tests will fail if you try; do not weaken the tests.)
- **Do not** add a second domain (nutrition / sleep / productivity). v1 is fitness only. Add domain #2 only after Section 12 H ("does it feel like a real coach") is an honest yes for fitness.
- **Do not** make nudges templated. If you find yourself writing a format string for nudge text, you're regressing D2 — push that work into the LLM with explicit variety guidance.
- **Do not** make the coach polite when it should refuse. The safety boundary's job is to **stop** prescribing on injury/medical/mental-health signals, not to caveat.

## Git workflow

- Working branch: `claude/youthful-cerf-SA0i9` (already pushed to `amersa64/exp`)
- Push protocol from the original session: `git push -u origin <branch>` with exponential backoff on network failure (2s, 4s, 8s, 16s). Do not force-push. Do not `--no-verify`.

## When to score the rubric

After every meaningful change. Update the README table honestly — including downgrades when you broke something. The scorecard is the conscience of the codebase. If you can't say where your change moved the needle, the change wasn't worth making.

## Starter prompt for the new session

> Continue development on The Coach. Read `spec.md`, `README.md`, and `HANDOFF.md` first. Verify the build (`python -m pytest backend` + `python -m cli.demo`), then [task 1: get the iOS app building in Xcode / task 2: build the Google Calendar OAuth adapter / etc.]. Honor the Section 11 anti-patterns. Update the README rubric scores when done.
