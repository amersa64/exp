# v1 → v2 migration map

Every v1 surface listed below, with where it goes in v2. Use this as the checklist when the design freezes and engineering work begins.

## Top-level structure

| v1 | v2 | What happens |
|---|---|---|
| 5-tab bar (Train · Summit · Milestones · Habits · Today) | 3-tab bar (Coach · Now · Becoming) | Coach is new and is the default landing. Train → Now (renamed, content mostly preserved). Summit + Milestones + Habits collapse into Becoming as scroll sections. Today is absorbed into Coach. |
| Default landing = Train | Default landing = **Coach** | Cold open shows the coach speaking, not a workout card. |

## Screen-by-screen mapping

### Connectivity (v1 `01-connectivity-states.md`)

| v1 | v2 |
|---|---|
| Loading screen, "Connecting / Reaching the brain on the wire" | Loading screen, **"Waking your coach."** |
| Unreachable screen with URLError dump | Unreachable screen with **"Your coach can't be reached. Check your connection."** |
| No timeout fallback | Add 5-second fallback to softer "this is taking a moment…" |

See `screens/09-onboarding-v2.md`.

### Intake (v1 `02-intake.md`)

| v1 | v2 |
|---|---|
| 8 questions, identity last | 9 questions, identity last |
| Q3 Injuries free-text + skip pill | Same — but rename the skip pill from "Nothing — I'm good" to **"All clear"** |
| Q5 Baseline squat with "I'm not sure" switch | Same |
| No question about past failures | **NEW Q8: "What killed your last attempt?"** — free text with examples carousel. Placed BEFORE identity statement. |
| Welcome tagline: *"A copilot that pushes when it matters…"* | New tagline: *"A coach who notices when you slip. And is still here when you come back."* |
| Submitting copy: "Building your program" | **"Putting your program together. One minute."** |
| Q1 back chevron disabled | **Enabled.** User can back out of intake entirely. |

See `screens/05-intake-v2.md`.

### Train tab → Now tab (v1 `03-train-tab.md` + `04-train-log-session.md`)

| v1 | v2 |
|---|---|
| Tab named "Train" | **Renamed "Now"** — clearer semantic, no Today/Train confusion |
| Default landing | No longer default landing — Coach tab is default |
| Toolbar shows currency + streak ("●23 · 3d") | **Toolbar shows votes only** ("Votes: 27"). Streak deleted. |
| "Schedule on calendar" button always visible | **Hidden** until F2 (Google Calendar OAuth) ships |
| "Bad day? Minimum dose" always shown | **Conditional surfacing only:** shown after 6pm with no log, OR when a slip pattern is detected, OR on a heavy-calendar day |
| Coach voice missing on log-session response | **Coach speaks back inline before dismiss** — see `screens/06-log-session-v2.md` |
| Friction placeholder: "What got in the way? (optional)" | **"e.g. kids meltdown at 6pm"** — placeholder is the example |
| Silent failure on send | **Inline error in the sheet; sheet stays open on error** |

See `screens/02-now-tab.md` and `screens/06-log-session-v2.md`.

### Summit tab → Becoming tab top section (v1 `05-summit-tab.md`)

| v1 | v2 |
|---|---|
| Standalone tab | Top scroll section of new Becoming tab |
| Three stat cards (Effort / Streak / Longest) | **Replaced with one VotesCard as primary, plus a small "weeks training" stat as secondary** |
| Streak prominent | Removed |
| Identity displayed as plaque | Identity displayed as **a thing the coach said to you**: "You said you want to be someone who shows up, even when tired." |
| Mountain hero visual | Preserved — but snow line drives off votes count, not currency |
| Silent failure on world load | Inline retry instead |

See `screens/03-becoming-tab.md`.

### Milestones tab → Becoming tab middle section (v1 `06-milestones-tab.md`)

| v1 | v2 |
|---|---|
| Standalone tab | Middle scroll section of Becoming tab |
| Flat list, untappable rows | Tappable rows → detail sheet with the coach's interpretation |
| Achievement is silent | First-view-after-achievement triggers a one-time inline narration on Becoming and a "from coach" line on Coach tab |
| Empty state generic | Coach-voice empty state: *"Milestones load when your program builds."* |

See `screens/03-becoming-tab.md`.

### Habits tab → Becoming tab bottom section (v1 `07-habits-tab.md`)

| v1 | v2 |
|---|---|
| Standalone tab | Bottom scroll section of Becoming tab |
| Single living-system card looks lonely | Re-rendered with the coach's plain assessment: *"Strength training: thriving. Don't change anything."* |
| No drill-in | Tappable → detail sheet with vitality trend + coach's read on what's driving it |
| Leaf metaphor unchanged | Preserved (no evidence to change yet) |

See `screens/03-becoming-tab.md`.

### Today tab → Coach tab (v1 `08-today-tab.md`)

This is the biggest folding move.

| v1 | v2 |
|---|---|
| Standalone tab in position 5 | **Becomes the Coach tab in position 1, default landing** |
| Multiple stacked cards (observation / last nudge / follow-ups / dev tick) | **Single coherent surface — one of 5 shapes** (Quiet / Prescription / Slip / Return / Pause-ack) |
| Dev "Tick now" button | Hidden behind `#if DEBUG` |
| Latest from the coach + From your coach | Folded into the single coach line for that shape |
| Follow-ups owed (amber) | Preserved — surfaced below the main shape, tappable |
| No slip-day intervention | **NEW Shape C** — see `screens/01-coach-tab.md` |
| No return-after-absence surface | **NEW Shape D** — see `screens/01-coach-tab.md` |

See `screens/01-coach-tab.md`.

### Nudge Reply sheet (v1 `09-nudge-reply.md`)

| v1 | v2 |
|---|---|
| 5 outcomes with verbose footer copy | 5 outcomes with **coach-voice footers** (see voice spec § 9) |
| Sheet shows no nudge context | **Adds nudge headline at the top** so the user knows what they're replying to |
| Result state: ripples + coach response + done button | Preserved — coach response stays first (it's the best moment in the app) |
| No deep-link after success | Add **"see what's next"** CTA → opens Now tab |

See `screens/07-nudge-reply-v2.md`.

### Settings (v1 `10-settings.md`)

| v1 | v2 |
|---|---|
| Backend URL shown | Hidden in production builds |
| User UUID shown | Hidden in production builds |
| Identity statement read-only | Preserved — read-only |
| Reset onboarding (clears client only) | **Replaced with "Start over" that ALSO resets the backend** (no more ghost programs) |
| No pause | **NEW: "Pause for a week" / "Pause for a month" / "End program"** |
| No human-handoff stub | **NEW: "Talk to a human coach"** row (placeholder UI; not wired in v2 unless a partner exists) |

See `screens/08-settings-v2.md`.

## New screens that don't exist in v1

| New screen | Where it lives | Triggered by |
|---|---|---|
| **Weekly Letter** | Full-screen modal | Sunday 18:00 push, or Coach tab "this week's letter" card |
| **Coach Shape C — Slip-day intervention** | Coach tab (a shape, not a separate screen) | 2 consecutive missed sessions |
| **Coach Shape D — Return after absence** | Coach tab (a shape) | 5+ days no verified event |
| **Coach Shape E — Pause acknowledgment** | Coach tab (a shape) | User triggered a pause from Settings |
| **Milestone detail sheet** | Modal from Becoming tab | Tap a milestone row |
| **Habit detail sheet** | Modal from Becoming tab | Tap a habit card |

## What v1 features become obsolete

- The "Today tab" as a navigable destination. Folded.
- The "Habits tab" as a navigable destination. Folded.
- The "Milestones tab" as a navigable destination. Folded.
- The toolbar currency badge with streak suffix. Replaced by votes-only.
- The "Tick now" button in production. Debug-only.

## Engineering implications (rough)

| Area | Effort |
|---|---|
| Backend: slip detection (consecutive miss counter + tick-time check) | Small — extends existing `Scheduler` logic |
| Backend: 5+ day absence detector | Small — query against last `VerifiedEvent` |
| Backend: pause state machine | Medium — new state, suppresses scheduler, adds resume hook |
| Backend: weekly letter generator | Medium — LLM call, new endpoint, push schedule |
| Backend: real `DELETE /user/{id}` for full reset | Small |
| iOS: tab refactor 5 → 3 | Medium — rebuild WorldView, route changes |
| iOS: Coach tab with 5-shape switching | Medium — new view with shape selector based on `coachState` |
| iOS: Weekly Letter screen + deep-link from push | Small |
| iOS: Becoming tab with 3 stacked sections + detail sheets | Medium |
| iOS: voice-spec-bound copy on every surface | Mostly content work; small per surface, large in aggregate |
| iOS: Settings — pause UI + handoff stub | Small |

## Risks called out elsewhere

See `screens/01-coach-tab.md` § Risks for the discoverability concern (can a new user find the workout?) and `README.md` for the three preconditions before any of this ships.
