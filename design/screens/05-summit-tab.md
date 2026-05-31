# 05 — Summit tab

The widest zoom of the world. Identity statement + the growing mountain + the numbers that prove it grew.

## Role

Zoom 1 of the four-level zoom (spec §6.1). The summit answers **"who am I becoming?"** — and it grows visually as verified events accumulate. The mountain's snow line rises with effort. The aurora warms with streak. The summit beacon pulses harder the longer the streak holds.

**Read-only (spec §6.3 / Principle 2.6).** Nothing on this screen can be tapped to compute or change state. Every number is derived server-side from `VerifiedEvent`s — this is the **mirror principle** rendered visually.

## Wireframe

```
┌─────────────────────────────┐
│ ⚙        Your summit    ●23 │  ← gear · title · currency badge
├─────────────────────────────┤
│         ✨                  │
│   WHO YOU'RE BECOMING       │  ← eyebrow
│                             │
│   Someone who shows up,     │  ← serif title (big, centered)
│   even when tired           │
│                             │
│   The summit grows with     │  ← muted subtitle
│   every verified session.   │
│                             │
│ ┌─────────────────────────┐ │  ← hero (rounded card, 260 high)
│ │  ✦  ·   . ✦ .  ✦   ·    │ │     starfield over sky
│ │     ·  ✦ ·     ·   ✦    │ │
│ │  ╱╲           ╱╲╱╲       │ │     back range (purple)
│ │ ╱  ╲╱╲   ╱╲ ╱      ╲     │ │
│ │      ╱╲▲╱╲   ◄ snow cap  │ │     front mountain
│ │     ╱▲▲▲▲╲      rising   │ │     w/ summit star
│ │    ╱▲▲▲▲▲▲╲              │ │
│ │   ╱  glow  ╲             │ │     ember/violet aurora
│ │  ╱──────────╲            │ │
│ └─────────────────────────┘ │
│                             │
│ ┌─────────────────────────┐ │  ← stats card (glass)
│ │  23   │   3    │   12   │ │     three numbers
│ │ Effort│ Streak │Longest │ │     (currency / streak / longest)
│ └─────────────────────────┘ │
│                             │
│ ┌─────────────────────────┐ │  ← votes card (glass)
│ │ 🏷  7 votes cast         │ │
│ │    for who you're        │ │
│ │    becoming              │ │
│ └─────────────────────────┘ │
├─────────────────────────────┤
│ 🏋 ⛰ 🚩 🌿 ☀                │  ← tab bar (Summit selected)
└─────────────────────────────┘
```

## Mountain visual semantics

| Property | Drives | Range |
|---|---|---|
| Snow line height | `currency / 50` (clamped) | growth 0 → 1 |
| Aurora intensity | `streak_days / 30` (clamped) | aura 0 → 1 |
| Summit beacon glow | `aura` (same as aurora) | pulses at all times |
| Star count | static (55 deterministic stars) | not data-driven |

These mappings are visual *reflections* of state — the world grew, and you can see it grew. The user cannot manipulate them.

## Content states

| State | Trigger | Visual |
|---|---|---|
| Ready | `world` loaded from backend | full render as above |
| Empty world | First load, no events yet | identity + flat mountain (snow=0) + zeroes |
| World load failed | `try?` returned nil — silent today | identity + zeroes (visually indistinguishable from empty) |

> Note: failure is silent because `refreshWorld()` is `try?`. A user with a stale or broken backend will see "0 effort, 0 streak" with no error. That's bad — they'll think their work didn't count.

## Enters from

- Tab bar → tap Summit
- Pull-to-refresh re-fetches `/world`

## Exits to

- Tab bar → any other tab
- Gear → Settings sheet
- (No tap targets on the hero itself.)

## UX questions

- **Identity statement is set once during intake and never edited.** Settings shows it read-only. Should the user be able to edit it? The spec frames it as the summit — changing it changes everything. Maybe an explicit "evolve your summit" ritual instead of a free edit?
- **Effort = "currency".** The word currency leaks the game-design model (§6.4) into a place where the user is supposed to think about *who they're becoming*. The Summit page calls it "Effort" — but the toolbar badge is "23 · 3d" which is currency · streak. Worth deciding: is the player's number on Summit called Effort or something else?
- **Three stat cards + one votes card** is a lot of numbers for a "who are you becoming" screen. Could Votes replace Effort entirely — since votes IS the spec's identity-aligned currency?
- **No mountain interactivity.** This is on purpose (mirror principle), but it might feel inert on a "hero" surface. Worth a subtle parallax on scroll? Tilt with gyroscope?
- **No timeline.** The mountain shows "now". It doesn't show "before". A long-term user with 90-day streak gets the same mountain as a 30-day streak (aura caps at 30). Is there a v2 where the summit grows beyond what the v1 visuals can show?
- **The Summit and Train tabs together reveal a tension**: Train answers "do this", Summit answers "this is why". Should Summit be *higher* in the tab order — the why before the what — or is current ordering (do first, reflect second) correct?
