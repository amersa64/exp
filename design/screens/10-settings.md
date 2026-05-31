# 10 — Settings sheet

The admin surface. Backend URL, identity statement (read-only), reset.

## Role

Settings is intentionally minimal. The Coach is not a settings-rich product — most of what would normally be a setting (notification frequency, training days, goal) is *coach state* and lives on the backend. This sheet exposes only:

- where the brain lives (backend URL)
- who you said you were becoming (identity, read-only mirror)
- the user ID
- a destructive escape hatch (reset onboarding)

The mirror principle (§6.3) applies: identity here is **shown**, not edited.

## Wireframe

```
┌─────────────────────────────┐
│                Settings  Done│  ← sheet nav (Done = ember)
├─────────────────────────────┤
│                             │
│ BACKEND                     │  ← group header eyebrow
│ ┌─────────────────────────┐ │
│ │ URL  http://127.0.0.1:  │ │  ← static row
│ │      8765               │ │
│ └─────────────────────────┘ │
│                             │
│ IDENTITY                    │
│ ┌─────────────────────────┐ │
│ │ Statement  Someone who  │ │  ← identity (read-only)
│ │            shows up,    │ │
│ │            even when    │ │
│ │            tired        │ │
│ │ ─────────────────────── │ │
│ │ User       {uuid…}      │ │
│ └─────────────────────────┘ │
│                             │
│ [·  ↺ Reset onboarding  ·]  │  ← ghost button, rose tint
│ Clears your identity        │
│ statement and intake        │
│ completion locally. The     │
│ backend still remembers     │
│ your program until you      │
│ reset its database.         │
│                             │
└─────────────────────────────┘
```

## Wireframe — reset confirmation

```
┌─────────────────────────────┐
│                             │
│   Reset onboarding?         │
│                             │
│   You'll go back through    │
│   intake. Your verified     │
│   history on the backend    │
│   is unaffected.            │
│                             │
│   [   Reset (destructive)  ]│
│   [        Cancel           ]│
└─────────────────────────────┘
```

(`confirmationDialog` — system sheet over the Settings sheet.)

## Settings rows today

| Group | Row | Type | Notes |
|---|---|---|---|
| BACKEND | URL | static text | Hardcoded; not editable |
| IDENTITY | Statement | static text | Read-only mirror of intake answer |
| IDENTITY | User | static text | UUID; for debugging |
| (no group) | Reset onboarding | destructive button | Clears local SessionStore only |

## Reset behavior

`Reset onboarding` only resets the **client**:
- `sessionStore.hasCompletedIntake = false`
- `sessionStore.identityStatement = nil`
- `sessionStore.userId` regenerates (?)
- App routes back to Intake on next render

It does **NOT** reset the backend. The brain still has the user's program, world state, and history. This means a user who resets and re-onboards may produce a **new** user record on the backend (depending on userId handling), creating a stale program server-side.

> This is a footgun. Worth either: (a) calling a backend `DELETE /user/{id}` on reset, or (b) renaming the button to "Start over (clears app, not backend)" so the user knows what they're doing.

## Enters from

- Any of the five tabs → gear icon in top-left toolbar

## Exits to

- **Done** → dismiss → return to the tab that opened it
- **Reset onboarding → confirm** → dismiss + reroute to Welcome (Intake)
- **Reset onboarding → cancel** → confirmation dismissed, settings sheet stays

## UX questions

- **The backend URL row is informational only.** A user with a network problem can't fix it here. For local dev, this is fine. For production, it shouldn't exist — there's no reason for a real user to know an IP.
- **Identity is unedictable.** Settings is the only place where identity is visible AFTER intake. If the user evolves ("I'm becoming someone who's actually strong, not just shows up"), there's no path to change it. Either add an explicit "evolve" path (which is intentionally heavy — see Summit tab notes) or accept identity is set-and-forget.
- **No notification settings.** No "snooze for the week", no "quiet hours". The brain handles restraint server-side, but a user-facing kill switch (for travel weeks, illness, deload) might be needed. Tip: the spec frames silence as a feature — so this might be a "tell the coach you're out for the week" affordance more than a toggle.
- **No HealthKit / Calendar connection management.** When those land, Settings is the natural home for connect/disconnect. The current sheet has no place for them — needs a new group.
- **Reset is dangerously easy.** One ghost button, one confirm. Worth typing the word "reset" to confirm? Or moving it behind a "Debug" disclosure?
- **No "sign out".** No account model exists (yet). When auth lands, this sheet grows considerably. Plan for that visual budget now.
- **Settings is reachable from all five tabs.** Good redundancy. But it means a gear icon eats top-leading toolbar space on every tab — could be moved to a "more" tab in the bar or to the Summit tab only.
