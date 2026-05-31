# 08 — Today tab

The narrowest zoom: what the coach has been saying, and what's owed back.

## Role

Zoom 4 (spec §6.1) + the nudge surfaces (§7). Today is the "inbox" of the coach: the latest observation, the last nudge, and any follow-ups owed. It is **the only tab where the coach speaks in its own voice** (the others render derived state).

This is where Rubric A4 (loop-closing) lives in the UI. When the coach asks something and the user doesn't answer, the unanswered ASK shows up here as a tappable follow-up.

## Wireframe — fully loaded

```
┌─────────────────────────────┐
│ ⚙          Today        ●23 │
├─────────────────────────────┤
│                             │
│ ┌─── tinted ember ────────┐ │
│ │ FROM YOUR COACH 〝       │ │  ← eyebrow
│ │                          │ │
│ │ You've squatted three    │ │  ← serif body (large)
│ │ Mondays in a row at the  │ │     LLM-authored observation
│ │ same load. Add five next │ │
│ │ session.                 │ │
│ │                          │ │
│ │ Surfaced because: load   │ │  ← muted reason
│ │ plateau on squat.        │ │
│ └─────────────────────────┘ │
│                             │
│ ┌─────────────────────────┐ │
│ │ LATEST FROM THE COACH 📣  │ │  ← eyebrow + when fired
│ │                  · 2h ago │ │
│ │ Tuesday lift — Full B    │ │  ← headline
│ │                          │ │
│ │ Squat 3×5 @ 150 lb,      │ │  ← body
│ │ Bench 3×5 @ 95 lb…       │ │
│ │                          │ │
│ │ After your morning       │ │  ← implementation intention
│ │ coffee, I will start     │ │     (italic, serif)
│ │ Full B at the garage.    │ │
│ │                          │ │
│ │ [Done]·  fired because:  │ │  ← outcome badge + reason
│ │  60-min calendar gap…    │ │
│ └─────────────────────────┘ │
│                             │
│ FOLLOW-UPS OWED ✉           │  ← section header
│ ┌─── tinted amber ────────┐ │
│ │ ↩  Tuesday lift          │ │  ← amber tinted card
│ │    You didn't get back   │ │     tappable → NudgeReplyView
│ │    to me — what got in   │ │
│ │    the way?         ›    │ │
│ └─────────────────────────┘ │
│ ┌─── tinted amber ────────┐ │
│ │ ↩  Mobility 5            │ │
│ │    Did you slot it in?  ›│ │
│ └─────────────────────────┘ │
│                             │
│ ┌─── glass ───────────────┐ │
│ │ 💻 Coach engine          │ │  ← dev card (subtle)
│ │ Trigger a tick to wake   │ │
│ │ the brain now (dev       │ │
│ │ affordance — replaces    │ │
│ │ APNs/cron locally).      │ │
│ │ [    Tick now    ]       │ │
│ └─────────────────────────┘ │
│                             │
├─────────────────────────────┤
│ 🏋 ⛰ 🚩 🌿 ☀                │
└─────────────────────────────┘
```

## Wireframe — empty/quiet day

```
┌─────────────────────────────┐
│ ⚙          Today        ●23 │
├─────────────────────────────┤
│ ┌─────────────────────────┐ │
│ │ 🌙  Coach hasn't pushed  │ │  ← empty-nudge card
│ │     yet today            │ │
│ │ Silence is a feature.    │ │     spec §7 — silence is OK
│ │ The brain fires only     │ │
│ │ when an opportunity      │ │
│ │ opens.                   │ │
│ └─────────────────────────┘ │
│                             │
│ ┌─────────────────────────┐ │
│ │ ✓ Nothing owed           │ │  ← empty follow-ups
│ │ The coach isn't waiting  │ │
│ │ on a reply.              │ │
│ └─────────────────────────┘ │
│                             │
│ ┌─ Coach engine ──────────┐ │
│ │ [    Tick now    ]       │ │
│ └─────────────────────────┘ │
└─────────────────────────────┘
```

## The four sections (in order)

| # | Section | When it shows | What it does |
|---|---|---|---|
| 1 | **From your coach** | `coachState.latestObservation` exists | ember-tinted card; the coach speaks |
| 2 | **Latest from the coach** | `coachState.lastNudge` exists OR program exists (empty card) | shows last fired nudge + outcome; or "no nudge yet" |
| 3 | **Follow-ups owed** | always (with loading / empty / list / failed) | amber-tinted; tappable rows → NudgeReplyView |
| 4 | **Coach engine** | always | dev affordance (Tick now); should hide in production |

## Content states

| Section | States |
|---|---|
| Observation | hidden / shown |
| Last nudge | hidden / empty-nudge card / nudge card |
| Follow-ups | loading / empty / list / failed (inline error card) |
| Coach engine | always shown today |

## Enters from

- Tab bar → tap Today
- Reactive: `coachStateChanged` notification → `WorldViewModel.refreshAll()` re-renders this tab if visible

## Exits to

- Tab bar → any other tab
- Gear → Settings
- **Tap a follow-up** → `NudgeReplyView` modal (medium/large detents)
- **Tick now** → fires `POST /dev/tick` → in-place refresh, no navigation

## UX questions

- **Today contains four very different things.** Coach observation (rare, high signal), last nudge (replay), follow-ups (interactive owed), dev tick (admin). That's a lot of jobs for one screen. The Train tab also surfaces last-nudge-shaped content. Decision: are Today and Train really one tab pretending to be two?
- **Follow-ups are the most interactive thing on the tab but live below the read-only nudge card.** If the user *only* opens Today to clear their queue, the queue should be on top.
- **The Tick now button is a dev affordance** that should not ship to a real user. Today there's no flag to hide it. Worth a `#if DEBUG` gate or a Settings toggle.
- **"From your coach" is a high-signal moment** — when it appears, it should feel rare and weighty. The current card style is the same shape as everything else, just tinted. Could it deserve a sheet/modal treatment instead of a card?
- **No history.** A user who saw a coach observation yesterday can't find it again. Should there be a "journal" view of past observations? The backend has them (`CoachState.journal`), the UI surfaces only the latest.
- **Push notifications mostly replace this tab's role.** A user with APNs working would see the nudge as a push, not need Today to find it. Once push is real, what does Today look like? Perhaps it collapses to *only* follow-ups + observation history.
- **The empty state ("Silence is a feature") is the best line in the app.** Keep that voice.
