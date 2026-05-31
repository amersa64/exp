# 01 — Connectivity states (loading + unreachable)

The two screens the user sees before the app is usable. Both are gates — they only resolve when the backend becomes reachable.

## Role

The Coach is a thin client (spec §8.3) — the brain is server-side. Until the brain is reachable, nothing else is safe to show because every other screen reads from the backend. These two screens make the dependency visible instead of producing empty content.

## Wireframe — Loading

```
┌─────────────────────────────┐
│                             │
│                             │
│                             │
│            ●                │  ← ember dot, pulses
│         (glow halo)         │
│                             │
│        Connecting           │
│  Reaching the brain on      │
│        the wire.            │
│                             │
│                             │
│                             │
│                             │
└─────────────────────────────┘
```

## Wireframe — Unreachable

```
┌─────────────────────────────┐
│                             │
│                             │
│            ⚠                │  ← amber triangle
│                             │
│   Can't reach the coach     │
│                             │
│   {error.localizedDescr…}   │  ← what went wrong
│   — check that the backend  │
│     is running and try      │
│     again.                  │
│                             │
│   [    Try again    ]       │  ← ember button
│                             │
│                             │
└─────────────────────────────┘
```

## Content states

| State | Trigger | Visual |
|---|---|---|
| Loading | App launch → `BackendHealth.probe()` running | pulsing ember + "Connecting" |
| Unreachable | `/healthz` failed or timed out | ⚠ + error message + Try again |
| Reachable | `/healthz` returned 200 | (this screen unmounts — see flow) |

## Enters from

- **App cold start** — always lands here first
- **Settings → Reset onboarding** doesn't re-trigger this; the backend probe is one-shot per session

## Exits to

- Loading → Loading (re-probe) → either Unreachable or the next gate (IntakeGate)
- Unreachable → user taps Try again → probe runs → resolves to Loading state again

## UX questions

- **Is the error message useful to a real user?** Right now it surfaces the raw URLError message (`"Could not connect to the server"`). For a non-technical user this might be scary or meaningless. Worth a friendlier wrapper?
- **Should Loading have a timeout escape?** If the probe never returns, the user is stuck on the pulsing dot forever. After ~5s we could fall through to Unreachable with a "this is taking longer than usual" message.
- **Is the unreachable state actionable enough?** "Try again" is one button. Should there be a "settings → check backend URL" affordance for the local-dev case where the URL is wrong? Note: backend URL is hardcoded today (see `10-settings.md`).
- **Once we ship a real cloud backend, does Unreachable even need to exist?** A production user with a working internet connection will never see it. Maybe Loading → quick spinner → Unreachable folds into a single "no connection" state.
