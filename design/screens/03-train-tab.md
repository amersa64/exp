# 03 — Train tab

The "what do I do now" surface. Default landing after intake. The most action-oriented screen in the app.

## Role

Train is the **in-app fallback for the loop** (PROMPT → EXECUTE → REPORT — spec §4.1). Without it, a user who finishes intake lands on a beautiful Summit with no way to act. Without APNs wired, this is also the only path to log a session and feed adaptation.

> Rubric C1 ("useful without opening") rests on APNs delivering the nudge. Train is the **in-app fallback** so the loop is end-to-end exercisable today.

## Wireframe — ready state (program prescribed)

```
┌─────────────────────────────┐
│ ⚙             Train      ●3 │  ← gear · title · currency badge
├─────────────────────────────┤
│ ┌─────── tinted ember ────┐ │
│ │ THE SCRIPT  📜          │ │
│ │ After my morning coffee,│ │  ← implementation intention
│ │ I will start  Full A    │ │     (cue → action → location)
│ │ at  the garage          │ │
│ └─────────────────────────┘ │
│                             │
│ UP NEXT  🔥                 │
│ Full A                      │  ← session name (display)
│  ⏱ 45 min   📅 7:30 AM      │  ← meta pills (time + when scheduled)
│                             │
│ ┌─────────────────────────┐ │
│ │ 1  Squat            3×5  │ │  ← exercise rows (glass card each)
│ │       145 lb · 180s rest │ │     bold number = index
│ │       Build a brace…     │ │     ember = volume
│ └─────────────────────────┘ │
│ ┌─────────────────────────┐ │
│ │ 2  Bench           3×5   │ │
│ │       95 lb · 180s rest  │ │
│ └─────────────────────────┘ │
│ ┌─────────────────────────┐ │
│ │ 3  Row             3×8   │ │
│ │       65 lb · 90s rest   │ │
│ └─────────────────────────┘ │
│                             │
│ ↗ When all sets clean,      │  ← progression rule
│   add 5 lb next session.    │
│                             │
│ [   ✓ Log this session  ]   │  ← primary cta (ember)
│ [·  📅 Schedule on cal.  ·] │  ← ghost cta
│                             │
│ ┌─── tinted amber ────────┐ │
│ │ ⚡ Bad day?              │ │  ← minimum-dose card
│ │ Do one set of squats at  │ │     (2-minute rule)
│ │ 95 lb. That's the vote.  │ │
│ │ [· I did the minimum ·]  │ │
│ └─────────────────────────┘ │
│                             │
├─────────────────────────────┤
│ 🏋 ⛰ 🚩 🌿 ☀                │  ← tab bar (Train selected)
└─────────────────────────────┘
```

## Wireframe — after logging (inline ripples banner)

When the user returns from the log sheet, a green-tinted ripples banner appears **above** The Script card:

```
│ ┌─── tinted emerald ──────┐ │
│ │ ✓ Logged                 │ │
│ │ +7 effort · streak: 1d · │ │  ← ripples (server-derived)
│ │ living system thriving   │ │
│ │                          │ │
│ │ Next session: +5 lb on   │ │  ← adaptation rationale
│ │ squat.                   │ │
│ └─────────────────────────┘ │
```

The banner persists until the next refresh (pull-to-refresh) loads a fresh `nextSession`.

## Wireframe — empty state (no program yet)

```
┌─────────────────────────────┐
│ ⚙             Train         │
├─────────────────────────────┤
│                             │
│            🏋                │
│                             │
│   Nothing prescribed yet    │
│                             │
│   Finish intake and the     │
│   coach will prescribe      │
│   your first session.       │
│                             │
└─────────────────────────────┘
```

(In practice this empty state shouldn't happen — the Intake gate blocks users from reaching tabs without a completed intake. It's a defensive fallback if intake-completion ever desyncs from program existence.)

## Content states

| State | Trigger | Visual |
|---|---|---|
| Loading | First mount, before `GET /next` returns | centered ember spinner |
| Ready | Backend returned a `NextSession` | Script + Up Next + exercises + CTAs |
| Empty | 409 from backend (no program) | empty-state card |
| Failed | URL/network error | full ErrorView with retry |

## Enters from

- Intake submit → success → land here (default landing)
- Any other tab → tap Train tab in the tab bar
- APNs nudge → reply sheet dismiss → may land back here (currently returns to previous tab)

## Exits to

- **Log this session** → `LogSessionSheet` modal → on send → returns + ripples banner appears
- **Schedule on calendar** → fires `POST /actions/{id}/schedule` → refresh → meta pill shows the new time
- **I did the minimum** → fires `POST /actions/{id}/log` with outcome=done, friction="minimum dose — 2-min rule" → ripples banner
- Tab bar → any other tab
- Gear icon → `SettingsSheet`

## UX questions

- **Is "Train" the right name?** The tab is the first in the bar but represents the *current prescribed action*. "Today" is also a tab, which is confusing. Consider: rename Train → "Now" and move the dev-tick + last-nudge content out of Today.
- **Three calls-to-action stacked.** Log / Schedule / Minimum dose. That's a lot to decide between. Could "Schedule" be inlined with the time pill ("📅 7:30 AM — tap to change")?
- **The minimum-dose card is always shown.** Should it surface conditionally (e.g. only when the user has missed yesterday, or after 8pm, or when HealthKit signals fatigue)?
- **Progression rule is one line at the bottom.** This is the user's promotion criteria — should it be more prominent, or is it correctly de-emphasized so it doesn't pressure?
- **No history view.** After logging, the previous session disappears. A user who wants to see what they lifted last Friday has to leave Train. Is this fine (the coach tracks; you don't have to), or does at-a-glance recall belong here?
- **The Script can read awkwardly** when the cue contains a comma or is multi-clause. Example: "After picking up the kids, then making dinner, I will…". Worth structuring the cue input as a noun-phrase prompt?
- **Schedule on calendar requires calendar OAuth** that isn't wired. Today this button silently no-ops or 500s. Hide until F2 is real?
