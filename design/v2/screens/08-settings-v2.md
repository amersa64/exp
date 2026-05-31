# 08 — Settings (v2)

The admin sheet. Adds pause-as-a-command, makes reset honest about the backend, adds a human-handoff stub.

## Role

Settings stays minimal — but in v2 it absorbs the most important new product mechanic: **rest is a command, not a side effect.** A user who needs a break has a button to ask for one. The coach honors it. No nagging push during pause, no streak guilt, no implicit failure.

The second important change: the v1 "Reset onboarding" button was a footgun — it cleared local state but the backend kept the user's program, creating ghost users. v2 makes reset honest.

## What changed from v1

| | v1 | v2 |
|---|---|---|
| Backend URL row | Shown (informational) | **Hidden in production builds** |
| User UUID row | Shown | **Hidden in production builds** |
| Identity statement | Read-only | Preserved — read-only |
| Reset onboarding | Cleared client only | **"Start over" — clears client AND backend** |
| Pause | Not possible | **"Pause for a week"** + "Pause for a month" rows |
| Human handoff | None | **"Talk to a human coach"** stub row |
| Notification preferences | None | **"Quiet hours"** row (10pm-6am default; configurable) |

## Wireframe

```
┌─────────────────────────────┐
│                Settings  Done│
├─────────────────────────────┤
│                             │
│ IDENTITY                    │
│ ┌─────────────────────────┐ │
│ │ You said you want to be │ │  ← read-only, coach-voice
│ │ someone who shows up,   │ │     framing
│ │ even when tired.        │ │
│ └─────────────────────────┘ │
│                             │
│ PROGRAM                     │
│ ┌─────────────────────────┐ │
│ │ ⏸  Pause for a week      │ │  ← coach goes silent,
│ │                          │ │     auto-resume Sunday
│ │ ─────────────────────── │ │
│ │ ⏸  Pause for a month     │ │  ← coach silent;
│ │                          │ │     user-triggered resume
│ │ ─────────────────────── │ │
│ │ ✕  End program           │ │  ← graceful exit
│ └─────────────────────────┘ │
│                             │
│ NOTIFICATIONS               │
│ ┌─────────────────────────┐ │
│ │ Quiet hours              │ │
│ │ 10:00 PM – 6:00 AM   ›   │ │  ← tap to edit
│ └─────────────────────────┘ │
│                             │
│ NEED MORE                   │
│ ┌─────────────────────────┐ │
│ │ 👤 Talk to a human coach │ │  ← stub for v2.x
│ │    Not built yet.    ›   │ │
│ └─────────────────────────┘ │
│                             │
│ [·  ↺  Start over       ·]  │  ← destructive
│                             │
│ This clears your program    │
│ and starts intake again.    │
│ Your past sessions stay     │
│ in your history.            │
│                             │
└─────────────────────────────┘
```

## Pause behavior — the key v2 addition

### "Pause for a week"

- Backend stores `pause.until = now + 7 days`.
- All scheduled nudges in the next 7 days are suppressed.
- The Coach tab switches to Shape E (Pause-ack — *"Paused. Back on Sunday."*).
- Next Sunday at the user's local 6am, the pause auto-clears. Coach tab returns to Shape A or B. A single welcome-back nudge fires at the user's normal first-of-day timing: *"Back on. Today: Full A."*

> One nuance: if the user opens the app during a pause, they see Shape E — but the rest of the app still functions. They can view their Becoming tab, see their session via Now (which also shows the pause state), open Settings to resume early. Pause = the coach is silent, not the app is locked.

### "Pause for a month"

- Backend stores `pause.until = now + 30 days`.
- Same suppression as week-pause.
- **Does NOT auto-resume.** After 30 days, the user opens the app and lands on Shape D (Return after absence) — three buttons: Back in / Give me a week / I'm done.
- The reason: a month is long enough that we shouldn't assume the user wants the same program. We let them tell us.

### "End program"

- Confirmation dialog: *"End your program? Your history stays. You can start a new one anytime."*
- If confirmed:
  - Backend marks the program archived (NOT deleted — preserves history).
  - The app routes to Welcome with a new "Start a new program" CTA.
  - All scheduled nudges cancelled.
- This is the **graceful exit**. Honest. A user who's done with this program should be able to *end it* without performing failure or uninstalling the app.

## Start over — the destructive button

```
"This clears your program and starts intake again.
 Your past sessions stay in your history."
```

Tap → confirmation dialog:

> **Start over?**
> 
> Your current program ends. You'll go through intake again. Past sessions stay.

If confirmed:
- Backend `DELETE /programs/current` (NEW endpoint — v1 didn't have this).
- Local SessionStore cleared.
- Route to Welcome → Intake.

> v1 cleared only the client state, leaving an orphan program server-side. v2 fixes that. The button label changes from "Reset onboarding" to **"Start over"** — clearer English, and "start over" implies a clean slate, which is what now actually happens.

## Quiet hours

Default: 10pm – 6am local. Editable via a small sheet:

```
┌─────────────────────────────┐
│ Cancel    Quiet hours       │
├─────────────────────────────┤
│                             │
│ Coach won't ping you        │
│ between these times.        │
│                             │
│ From    [ 10:00 PM ]  ›     │  ← time picker rows
│                             │
│ To      [  6:00 AM ]  ›     │
│                             │
│ [        Save         ]     │
└─────────────────────────────┘
```

Fed to the nudge scheduler — pushes within this window are deferred to the window edge or skipped.

## Talk to a human coach — the stub

v2 doesn't ship a real human-handoff partnership. But the row exists so:

1. The UI affordance is established (users see "real coaches exist as an escape valve").
2. Spec Principle 8 (know the edge of competence) has a visible product expression.
3. When we partner with a coaching service later, the row activates.

In v2, tapping shows a sheet:

```
   Not built yet.
   
   When this is built, this is where 
   you'd be connected with a real 
   strength coach for a session.
   
   For now, if something needs human 
   eyes — a doctor, a trainer, a 
   therapist — go see one.
   
   [    Got it    ]
```

The voice on that empty state is intentional. Marcus refers, doesn't pretend to be a doctor. The stub maintains the voice contract even when the feature isn't real yet.

## What v2 Settings does NOT have

- **Edit identity statement.** Decided no. If users push for it, evaluate v2.1.
- **Notification frequency tuning.** The brain handles restraint; we don't expose dials.
- **Calendar / HealthKit connection management.** Until F1/F2 ship, no point. When they ship, they get their own group.
- **Account / sign-in.** No auth model in v2.
- **Theme / dark mode.** App is dark-mode-only by design.
- **App version / build number.** Production builds; not user-facing.

## States

Settings sheet has no complex states — it's a static list of rows. Each row may open its own sheet (Quiet hours, human handoff stub) or trigger a confirmation dialog (Pause options, Start over, End program).

## Engineering notes

- **Backend endpoints needed:**
  - `POST /programs/pause { duration: "week" | "month" }`
  - `POST /programs/resume`
  - `POST /programs/end`
  - `DELETE /programs/current` (for Start over)
  - `PATCH /preferences/quiet_hours { from, to }`
- **Coach state changes** propagate through the existing `coachStateChanged` notification, so all tabs refresh after pause / end / resume.
- **Pause state** must be checked by the nudge scheduler before firing any push.

## Risks

- **"End program" tapped accidentally.** Confirmation dialog wording matters. *"End your program? Your history stays."* — the second clause is the safety release valve.
- **"Pause for a month" being too easy a path out.** A user who selects this might not come back. But the alternative — punishing them for needing a break — is worse. Trust the user. Real-world data will tell us whether month-pausers return or churn.
- **Quiet hours interacting with timezones / travel.** A user who travels across timezones should have their quiet hours follow them. The device's local timezone is the source of truth. Add a "follow device timezone" toggle if users report issues.

## Open questions

- Should Settings be reachable from every tab, or only the Coach tab? Current: every tab (gear in top-leading). Reducing to only Coach tab would reduce visual clutter on Now and Becoming but cost users a step. Probably keep on every tab for v2.
- Should we have a "Snooze coach for a day" option, between "ignore a nudge" and "pause for a week"? A one-day pause is a single missed session, which the slip detector handles anyway. Probably not worth a new affordance.
- Should pause auto-resume include a coach message *before* the resume (e.g. Saturday evening, "I'm back tomorrow")? Possibly — but the surprise of opening Sunday and finding the coach ready might be nicer than a heads-up that adds anticipation pressure. Test with users.
