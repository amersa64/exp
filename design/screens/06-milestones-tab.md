# 06 — Milestones tab

The list of waypoints between today and the summit.

## Role

Zoom 2 of the four-level zoom (spec §6.1). Milestones are the program's structured ladder — each row a concrete, named achievement the brain has prescribed. Achieved milestones light up; future ones sit quietly waiting.

The milestone list is **server-derived** from the persona's program. A novice linear-progression persona might produce milestones like "Squat 5×5 at bodyweight", "Squat 5×5 at 1.5× bodyweight", "Hit 8 weeks unbroken". The user doesn't author these — they appear when the program builds.

## Wireframe — ready state (mixed achieved + pending)

```
┌─────────────────────────────┐
│ ⚙       Milestones      ●23 │
├─────────────────────────────┤
│                             │
│ ┌─────────────────────────┐ │
│ │ ●  Squat 5×5 at body-    │ │  ← achieved (filled ember circle
│ │     weight               │ │     w/ checkmark)
│ │     You hit this on      │ │
│ │     {date}.              │ │
│ └─────────────────────────┘ │
│                             │
│ ┌─────────────────────────┐ │
│ │ ○ 🚩 Squat 5×5 at 1.25×  │ │  ← pending (outlined circle
│ │     bodyweight           │ │     w/ flag)
│ │     Next target on the   │ │
│ │     squat ladder.        │ │
│ └─────────────────────────┘ │
│                             │
│ ┌─────────────────────────┐ │
│ │ ○ 🚩 Eight consecutive   │ │
│ │     weeks of training    │ │
│ │     Builds the habit     │ │
│ │     before the body.     │ │
│ └─────────────────────────┘ │
│                             │
│ ┌─────────────────────────┐ │
│ │ ○ 🚩 …                   │ │
│ └─────────────────────────┘ │
│                             │
├─────────────────────────────┤
│ 🏋 ⛰ 🚩 🌿 ☀                │
└─────────────────────────────┘
```

## Wireframe — empty state (no milestones yet)

```
┌─────────────────────────────┐
│ ⚙       Milestones      ●0  │
├─────────────────────────────┤
│                             │
│            🚩               │
│                             │
│   No milestones yet         │
│                             │
│   Once your program is      │
│   built, you'll see way-    │
│   points here.              │
│                             │
└─────────────────────────────┘
```

## Wireframe — loading

```
┌─────────────────────────────┐
│ ⚙       Milestones          │
├─────────────────────────────┤
│                             │
│                             │
│            ⟳ (spinner)      │
│                             │
└─────────────────────────────┘
```

## Wireframe — failed

```
┌─────────────────────────────┐
│ ⚙       Milestones          │
├─────────────────────────────┤
│            ⚠                │
│  Couldn't load milestones   │
│  {error message}            │
│  [    Try again    ]        │
└─────────────────────────────┘
```

## Content states

| State | Trigger | Visual |
|---|---|---|
| Loading | First mount or refresh | centered spinner |
| Ready (filled) | Backend returned ≥1 milestone | list of cards |
| Ready (empty) | Backend returned [] | flag icon + "No milestones yet" card |
| Failed | Request error | inline ErrorView w/ retry |

## Enters from

- Tab bar → tap Milestones
- Pull-to-refresh

## Exits to

- Tab bar → any other tab
- Gear → Settings
- (Milestone rows are not tappable today.)

## UX questions

- **No detail on tap.** A milestone row is purely informational. A user who wants to know "what does *Squat 5×5 at 1.25× bodyweight* mean in lb for me?" can't drill in. Worth making rows tappable to a detail sheet?
- **No grouping by category.** Currently flat list. With multiple personas (or just a deeper fitness program: lower-body, upper-body, conditioning), the list could grow long. Consider grouping by lift or by horizon (next / this month / this quarter / aspirational).
- **No timeline / ETA.** A milestone has no "you're 60% of the way" indicator. The user has no sense of distance. Is that intentional (the spec emphasizes the *act* over the destination)? Or is a progress affordance worth the risk of becoming a tracking app?
- **"Achieved" celebrations are absent.** A milestone going from pending → achieved is a peak moment — but nothing in the app marks it. No animation on first view of an achievement, no card surfaced on Today. Worth a "you hit a milestone" ribbon on Summit, or a one-time burst when the user opens this tab post-achievement.
- **Where do milestones come from textually?** The strings ("Squat 5×5 at bodyweight") are LLM-generated against the persona. A bad sample could produce inconsistent or weird phrasing. Worth defining a milestone *schema* (lift, weight-formula, condition) and letting the UI compose the string for consistency.
- **Conflict with the spec's zoom hierarchy.** Spec §6.1 puts Milestones as zoom 2 — *between* Summit (zoom 1) and Habits (zoom 3). But the tab is in position 3 (after Train and Summit). Does the user actually read it as "the second-widest view"? Or is it just a list?
