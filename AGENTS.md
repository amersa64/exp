# The Coach — agent map

> Goal of this doc: let an agent picking up one task **read only the sections
> relevant to that task** without grepping the repo. Skim "Where to look" to
> find your area; skim "Conventions" once; then jump straight to the named
> files. Don't read the whole code base.

## What this is

iOS coaching app. Backend is a FastAPI brain that builds a personalized training
program; iOS is a SwiftUI client. The user picks one of 5 goals (strength /
build muscle / lose weight / age well / 75-Hard discipline) → week 1 is
**calibration** (5 short assessments) → week 2+ is the real program with loads
derived from observed numbers. Identity-first ("I am someone who…"), with
"every action is a vote" surfaced on the Summit tab.

## Tech

- **backend/**: Python 3.11, FastAPI + Uvicorn, Pydantic. Entry: `backend/api/app.py`. LLM provider: OpenAI gpt-4o-mini.
- **Persistence**: `coach.store.make_store()` picks the backend. Prod runs on **Supabase Postgres** when `SUPABASE_DB_URL` is set (`coach/pg_store.py`, transaction pooler :6543); otherwise local **SQLite** (`coach/store.py`) — the default for tests + local dev. Both expose the identical method surface; mirror integrity lives in `save_world` on both. JSON-blob schema (`schema_postgres.sql`). Migrate SQLite→PG with `python -m coach.migrate_sqlite_to_pg coach.db`.
- **ios/**: SwiftUI, iOS 26, XcodeGen-managed (`ios/project.yml`). Entry: `ios/TheCoach/`.
- Backend tethered to Mac on LAN — iOS talks to `192.168.87.31:8766`.

## Where to look (by feature)

Pick the section that matches your task. Only read those files.

### Onboarding / intake
- `backend/coach/personas/<persona>.py` → `_intake()` returns the questions per goal.
- `backend/coach/lifecycle.py` → `Coach.record_intake()` (LLM derives a profile from free-text answers).
- `ios/TheCoach/Views/IntakeView.swift` — the multi-step intake screen.
- When **adding intake questions**: update the persona's `_intake()` + (if a benchmark needs it) `calibration.benchmark_user_factors()`.

### Calibration phase (week 1 assessment)
- `backend/coach/calibration.py` — Epley 1RM, benchmark tables (sex × age × bw → percentile/label), `lifting_calibration_days()` (shared 5-session battery for the 4 lifting personas) + `longevity_calibration_days()` (functional probes).
- `backend/coach/personas/<persona>.py` — each persona's `_transition_to_active()` sets starting loads from `program.calibration_results`.
- `backend/coach/models.py` — `ProgramState.phase` / `calibration_index` / `calibration_results`.
- `ios/TheCoach/Views/TrainView.swift` — `CalibrationBanner` + `LogSessionSheet` (structured "top set: reps × lb" inputs when `isCalibration`).

### Active programs (the 5 personas)
- `backend/coach/personas/strength.py` — Starting-Strength-style A/B, 3 days/wk.
- `backend/coach/personas/hypertrophy.py` — Upper/Lower 4 days/wk, double progression on 8-12 reps.
- `backend/coach/personas/conditioning.py` — 3 lift + 2 cardio, 5 days/wk.
- `backend/coach/personas/longevity.py` — full-body 2-3x/wk, glacial progression, plain-English notes, functional milestones.
- `backend/coach/personas/discipline.py` — 6 days/wk two-a-days, streak + hard reset on miss, sharper voice; safety overrides the contract.
- All personas share `personas/base.Persona` and are registered in `personas/__init__.py` (`PERSONAS` dict + `_GOAL_TO_DOMAIN` mapping).

### Train tab (UI for the prescribed session)
- `ios/TheCoach/Views/TrainView.swift` — `SessionContent`, `SessionHeader`, `ExerciseRow`, `SwapSheet` (per-exercise swap UI), `LogSessionSheet`.
- API contract in `ios/TheCoach/Models/Hierarchy.swift` (NextSession, PrescribedSession, ExercisePrescription).

### Summit tab (identity + votes hero)
- `ios/TheCoach/Views/WorldView.swift` — top-level TabView; Summit / Milestones / Habits / Today tabs.
- `ios/TheCoach/Views/PelletFlowHero.swift` — the hero animation. Current concept: identity statement at base → flame whose brightness scales with streak → embers rising → each cast vote = a persistent star in the sky (cap 90 visible). Respects `accessibilityReduceMotion`.

### Coach voice + journal (LLM-driven)
- `backend/coach/lifecycle.py` — `Coach.adapt()` rewrites the deterministic Python rationale into Marcus's voice. `compose_coach_response()` is the per-log reply.
- `backend/coach/journal.py` — narrative memory; every meaningful event appends one LLM-authored line, fed back as context.
- `backend/coach/llm.py` — provider wrapper (currently OpenAI gpt-4o-mini).
- `design/voice/` — the Marcus voice spec + denylist. Read this before touching coach-facing strings.

### Dev tools (fast iteration)
- `backend/coach/dev_scenarios.py` — named scenarios (fresh, mid-calibration, active+50 votes, streak-broken, etc.); `apply_scenario()` wipes a user and seeds it directly.
- `ios/TheCoach/Views/DevScenarioSheet.swift` — picker UI behind the wand-and-stars button on the Summit toolbar.
- Endpoints: `GET /dev/scenarios`, `POST /dev/seed`, `POST /dev/tick` (one scheduler tick).

### Models / persistence
- `backend/coach/models.py` — Identity, Milestone, Habit, AtomicAction, ProgramState, Nudge, WorldState, ExercisePrescription.
- `backend/coach/store.py` — SQLite wrapper. Mirror-integrity enforced on `save_world()`; bypass only via `dev_force_save_world()`.

### Backend API surface
- `backend/api/app.py` — routes. Key ones: `/intake/questions`, `/intake/submit`, `/session/next`, `/session/{id}/log`, `/nudge/{id}/reply`, `/world`, `/identity`, `/milestones`, `/dev/seed`.
- **Auth** (`_auth_gate` middleware): set `COACH_API_TOKEN` → all routes except `/healthz` require `Authorization: Bearer <token>`; unset → open (local/test default). `/dev/*` auto-disabled when the token is set unless `COACH_ENABLE_DEV=1`. Clients (iOS, the `/scheduler/tick` cron) must send the bearer header.

## Conventions (read once)

- **No emojis in code** unless the user explicitly asks.
- **snake_case JSON** ↔ camelCase Swift. iOS decoder uses `.convertFromSnakeCase`. **Avoid digits in field names** — Swift's converter doesn't round-trip them cleanly (`est_1rm_lb` → `est1RmLb` which won't match `est1rmLb`).
- **Theme palette**: `Theme.ember` (orange), `Theme.gold`, `Theme.amber`, `Theme.emerald`, all over `AtmosphericBackground()` (deep plum-night). Cards: `.glassCard()` / `.glassCardTinted(Theme.X)`.
- **WorldState mirror integrity**: `world.grow(event, action)` is the only path that mutates the world (currency, streak, votes). The store's `save_world()` enforces this. Dev-only escape hatch: `dev_force_save_world()`.
- **Coach voice ("Marcus")**: short sentences, no jargon, no "journey", no moralizing. Each persona overlays a small voice variation on this base (longevity warmer, discipline sharper). See `design/voice/`.
- **New persona**: add the file under `personas/`, register in `personas/__init__.py` (`PERSONAS` + `_GOAL_TO_DOMAIN`), expose `calibration_length` if it does calibration.
- **New iOS files**: run `xcodegen generate` from `ios/` so `project.pbxproj` picks them up — Xcode build will fail with "cannot find type X in scope" otherwise.
- **Cross-VM refresh**: `NotificationCenter.default.post(name: .coachStateChanged, object: nil)` fires after server-mutating ops. View models listen and re-fetch.

## Common commands

```bash
# --- backend ---
cd /Users/amer/productivity/the-coach
kill $(lsof -tiTCP:8766 -sTCP:LISTEN 2>/dev/null) 2>/dev/null; sleep 1
source .venv/bin/activate
PYTHONPATH=backend nohup python -m uvicorn api.app:app \
  --host 0.0.0.0 --port 8766 > /tmp/coach-backend.log 2>&1 &
sleep 5 && curl -sS http://127.0.0.1:8766/healthz

# --- backend tests ---
source .venv/bin/activate && python -m pytest backend -q

# --- iOS build + install (real device) ---
cd ios
xcodegen generate    # ONLY if you added/removed .swift files
xcodebuild -project TheCoach.xcodeproj -scheme TheCoach -configuration Debug \
  -destination "generic/platform=iOS" -derivedDataPath build/derived build
xcrun devicectl device install app \
  --device BBE04447-011F-51C1-832A-718F0016326C \
  build/derived/Build/Products/Debug-iphoneos/TheCoach.app

# --- tail backend log ---
tail -f /tmp/coach-backend.log
```

## Briefing a sub-agent

Paste this when launching a parallel agent, swapping `[TASK]` and `[SECTION]`:

> Read `/Users/amer/productivity/the-coach/AGENTS.md` first. Your task:
> **[TASK]**. The relevant section is **"Where to look → [SECTION]"**.
> Read only the files listed there + the Conventions block. Don't grep the
> rest of the repo unless you hit a real unknown (then ask before exploring).
>
> Constraints:
> - Don't touch files outside your section without surfacing why.
> - Run tests if you changed backend; build the iOS app if you changed Swift.
> - Don't install on device — I'll handle that.
>
> Report back: what you changed (files + key decisions), what you verified,
> and anything you chose NOT to do with a one-line reason.

For independent parallel work, give each agent a different section. Two
agents on the same section will silently overlap — the file system shows
both edits but neither knows about the other.

## Known caveats / not yet built

- **Becoming-tab summary card** — backend returns `calibration_results` per /session/next but iOS doesn't decode it yet (typed model is fiddly under `.convertFromSnakeCase` + digit-containing keys). Add a custom decoder when this card lands.
- **APNs push** — not wired. `POST /dev/tick` is the in-app substitute.
- **HealthKit** — not wired. Discipline's `_looks_like_exhaustion` adaptation hook exists but the sleep signal isn't reaching it yet.
- **Photo block** (discipline template) — designed in `design/v2/templates/05-discipline.md`, not built.
- **Cycle picker UI** (discipline: 75 / 30 / open-ended) — defaults to 75-classic for now.
- **Coach letter at calibration completion** — would explain the emphasis pick to the user on Becoming tab. Not built.
