# 09 — Onboarding (welcome + connectivity)

The four pre-intake surfaces, in coach voice. Small deltas from v1, but tonally important — these are the very first frames a user sees.

## Surfaces in this file

1. Backend loading (cold start)
2. Backend unreachable (connectivity error)
3. Welcome (the very first user-driven moment)
4. Submitting (post-intake, building the program)

All four use the standard `AtmosphericBackground()` and minimal chrome. They are the brand's first impression. Copy is the only thing that meaningfully changes between them, and copy is voice.

## 1. Backend loading

```
┌─────────────────────────────┐
│                             │
│                             │
│            ●                │  ← pulsing ember dot
│         (glow)              │
│                             │
│       Waking your coach     │  ← v2 copy
│                             │
└─────────────────────────────┘
```

| Element | v1 | v2 |
|---|---|---|
| Primary copy | "Connecting" | **"Waking your coach"** |
| Secondary copy | "Reaching the brain on the wire." | (none — primary line is enough) |
| Timeout fallback | (none — pulses forever) | **After 5 seconds, swap to "Still trying…"** |
| After 15 seconds | (none) | Fall through to Unreachable state |

The dev-poetic "reaching the brain on the wire" is gone. A real user doesn't know what *the brain* is. *Waking your coach* is in-voice, sets the right mental model, and is shorter.

## 2. Backend unreachable

```
┌─────────────────────────────┐
│                             │
│            ⚠                │
│                             │
│  Your coach can't be        │  ← v2 copy
│  reached.                   │
│                             │
│  Check your connection.     │
│                             │
│  [    Try again     ]       │
│                             │
└─────────────────────────────┘
```

| Element | v1 | v2 |
|---|---|---|
| Title | "Can't reach the coach" | **"Your coach can't be reached."** |
| Body | Raw `URLError.localizedDescription` + "— check that the backend is running and try again." | **"Check your connection."** |
| Retry CTA | "Try again" | Same |

The raw URLError dump leaks engineer reality into the user surface. *"Could not connect to the server"* doesn't mean anything to a normal user — and worse, it implies the user did something wrong. In v2 we own it: *the coach can't be reached.* Not the user's fault. Simple instruction. Done.

## 3. Welcome

```
┌─────────────────────────────┐
│                             │
│            ⛰                │  ← mountain icon, glowing
│         (radial glow)       │
│                             │
│       The Coach             │  ← display, rounded, heavy
│                             │
│  A coach who notices when   │  ← v2 tagline
│  you slip. And is still     │
│  here when you come back.   │
│                             │
│   [    Get started      ]   │  ← ember CTA
│                             │
│  Five minutes. Mostly       │  ← v2 caption
│  questions. Like meeting    │
│  a new trainer.             │
│                             │
└─────────────────────────────┘
```

| Element | v1 | v2 |
|---|---|---|
| Tagline | "A copilot that pushes when it matters and stays out of the way when it doesn't." | **"A coach who notices when you slip. And is still here when you come back."** |
| CTA caption | "A few quick questions — about a minute." | **"Five minutes. Mostly questions. Like meeting a new trainer."** |
| CTA label | "Get started" | Same |

### Why this tagline matters

The tagline is the **single most important sentence in the app's marketing surface**. It is what gets read on the App Store. It is what the user sees first. It has to do two jobs:

1. Differentiate from the tracker shelf.
2. Promise the thing the dropout-prone user has never been promised.

"A copilot that pushes when it matters and stays out of the way when it doesn't" (v1) is *technically true* but reads as generic AI-app copy. It doesn't address the user's actual pain (dropout) or distinguish us from the next "AI copilot" app.

v2: *"A coach who notices when you slip. And is still here when you come back."* — addresses the **specific failure mode** that kills habit-tracker users (the slip), and **promises the specific behavior** competitors don't offer (we don't quit on you). The second sentence is the moat. Read it aloud — it sounds like a friend talking.

### Why "five minutes" not "one minute"

Q8 (past failure) extends intake by ~90 seconds. We could fudge and still say "a minute" — but the user who set an expectation of a minute and gets five will resent it. Honesty about time is part of the trust contract. *"Five minutes. Mostly questions."* signals the shape (mostly clicking, not typing) and the duration (longer than a tracker, shorter than a doctor).

The "like meeting a new trainer" framing primes the right mental model. A trainer interview takes time; you don't expect it to be 30 seconds.

## 4. Submitting

```
┌─────────────────────────────┐
│                             │
│           ⛰                 │
│        (spinning ring)      │
│                             │
│   Putting your program      │  ← v2 copy
│   together. One minute.     │
│                             │
└─────────────────────────────┘
```

| Element | v1 | v2 |
|---|---|---|
| Title | "Building your program" | **"Putting your program together. One minute."** |
| Subtitle | "This usually takes a second." | (merged into title) |
| Failure | Full ErrorView "Couldn't build your program" + retry | **"Something's not working. Try again in a minute." + retry** |

*"Building your program"* is engineer voice ("building" implies code/components). *"Putting your program together"* is coach voice — the same word a trainer would use looking at a notebook. *"One minute"* sets honest expectations.

Failure copy gets the Marcus treatment: terse, no theater, no apology.

## Order of frames the first-time user sees

```
1. App icon tap
2. Backend loading (1-2s typical, falls through to Unreachable if >15s)
3. Welcome
4. (tap Get started)
5. Intake Q1
... Q9
6. Submitting (~3-5s typical)
7. Coach tab — Shape A or B, first prescription
```

Total time, first-time user, happy path: ~7 minutes. v1 was ~5 minutes (8 questions). The extra two minutes are Q8 + a slightly slower welcome.

Worth it.

## What didn't change

- The mountain icon and ember palette are preserved across all four surfaces.
- The radial glow animation on the Welcome screen is preserved.
- The spinning ring on Submitting is preserved.
- The pulsing dot on Loading is preserved.
- The Try again button styling matches everywhere.

Visually, a v1 user and a v2 user would see basically the same shapes. What changes is what the shapes *say*.

## Risks

- **The Loading screen's 15-second fall-through to Unreachable.** A user on a slow but working connection might trip this incorrectly. Mitigation: a backend health probe response is a tiny payload (<1KB). If 15 seconds isn't enough, the user is genuinely offline. Tune in prod.
- **The "five minutes" promise.** If intake actually takes longer (we run user studies and find it averages 7 min), the promise is broken. Mitigation: design intake for actual ≤5 min completion; trim questions if needed.
- **The welcome tagline is two sentences, not one.** Slightly longer to read on the App Store screenshot than v1's single sentence. Trade: punchier and more specific. Probably worth it. Test against single-sentence variants in A/B if we want to be rigorous.

## Open questions

- Should the Welcome screen optionally show a 5-second auto-rotating sample of one of Marcus's lines (e.g. *"Three sessions this week. Most you've done."*) — to demonstrate the voice rather than just describe it? Possibly — but might add complexity without clarity. Defer.
- Should the Welcome screen carry a "log in" CTA for returning users on a fresh device? Not v2 — no auth model yet.
- Should the Unreachable screen offer a "use offline" mode (read past content, queue actions)? Not v2 — the brain lives server-side and offline mode would require a sync model we don't have.
