# Pellet flow — the relationship made visible

A live, ambient visualization of what the coach is actually doing for the user. Pellets fall from the user's potential at the top, pass through (or get caught at) specific friction points along the way, and accumulate in a cup at the bottom representing their cast votes. The visual is **not decorative** — every element is bound to real data and updates over time as the user lives with the coach.

Inspired by the [Strawberry.me career-coach ad](https://strawberry.me/) split-screen visual, but reframed: we don't show "without coach vs. with coach" side-by-side. We show **only the with-coach side, on the user's data, growing day by day**.

## The single sentence

> A user opens the Becoming tab and *sees* their own coach doing the work — barriers holding, pellets accumulating, friction points labeled with their actual patterns. The mountain hero said "this is your summit"; the pellet flow says "this is how you're getting there, and here's the proof."

## Where it lives

**Replaces the mountain hero on the Becoming tab.** The mountain metaphor (peak = identity, snow line rises with progress) was decorative; the pellet flow is *informative*. We keep the mountain conceptually — the cup at the bottom is labeled with the identity statement, so it reads as the foundation of the user's summit — but the visual surface area becomes the pellet flow.

The mountain doesn't disappear from the brand entirely. It stays:
- As the app icon (already shipping)
- In the Welcome screen
- In a smaller secondary placement on Settings (Identity section)

> **Decision to revisit:** if testing shows users miss the mountain, we can render a low-opacity mountain silhouette *behind* the pellet flow as a static backdrop. Adds production cost but preserves both metaphors. Start without it.

## Wireframe

```
┌─────────────────────────────┐
│ ⚙        Becoming      ●27 │
├─────────────────────────────┤
│                             │
│ FROM YOUR COACH ✨           │
│ You said you want to be     │
│ someone who shows up,       │
│ even when tired.            │
│                             │
│ ┌────────── hero ─────────┐ │
│ │       ╲       ╱           │ │  ← funnel
│ │        ╲     ╱            │ │     (your potential)
│ │         ╲___╱             │ │
│ │           |               │ │
│ │           .               │ │
│ │           .               │ │
│ │           .               │ │
│ │  ━━━━━━━━━━━━━━━━━━━━━    │ │  ← BARRIER 1 (red)
│ │  Tue work crunch          │ │     friction label
│ │           .               │ │
│ │          ..               │ │  pellets flow,
│ │          ..               │ │  some leak out
│ │     ●    ..               │ │  to the sides
│ │  ━━━━━━━━━━━━━━━━━━━━━    │ │  ← BARRIER 2
│ │  Body's off                │ │
│ │          ...              │ │
│ │   ●     ...               │ │
│ │         ...               │ │
│ │  ━━━━━━━━━━━━━━━━━━━━━    │ │  ← BARRIER 3
│ │  Friday lapse              │ │
│ │         ....              │ │
│ │         ....              │ │
│ │    ╭───────────╮          │ │  ← cup (your votes)
│ │    │██████████ │          │ │
│ │    │██████████ │          │ │
│ │    │██████████ │          │ │
│ │    ╰───────────╯          │ │
│ │     27 · your summit       │ │
│ └─────────────────────────┘ │
│                             │
│ STATS STRIP                 │  ← existing components below
│ MILESTONES                  │
│ HABITS                      │
└─────────────────────────────┘
```

Vertical orientation (Strawberry's is also vertical but compressed). Hero is ~360pt tall on iPhone.

## What's bound to data

Every element on this surface traces to a real value. **No decoration that isn't earned.**

| Element | Data source |
|---|---|
| Funnel (top) | Always full — represents identity-as-potential, not measured |
| Pellets falling rate | Constant ambient (1/sec) — represents the user's *intent* over time |
| Stray pellets leaking (left/right of path) | Inactive barriers let some through; visual approximation of "without intervention" |
| Friction labels (3 of them) | See § Friction label generation below |
| Red barrier active | Coach has intervened on this friction in the last 7 days (slip-day fired, minimum-dose shown, follow-up rescued the user) |
| Pellets in cup | `world.votes_cast` (the same field already on Becoming) |
| Cup label | "{votes} · your summit" — links back to identity |
| Pellet flash on barrier | A coach intervention just fired for this friction (animation event) |

## Friction label generation — 3 phases

The friction labels are what makes this **ours**, not Strawberry's. They name the user's specific failure modes back to them.

### Phase 1 (MVP): Generic three

```
Barrier 1: Schedule conflicts
Barrier 2: Tired days
Barrier 3: Lost momentum
```

Used for new users with fewer than 5 sessions logged. Ships day 1.

### Phase 2 (Data-driven): Top three from friction reports

When the user has logged 5+ friction notes, cluster them and surface the most common three. Example output for a user who frequently types "kids meltdown", "too tired after work", and "didn't sleep":

```
Barrier 1: After-work crashes
Barrier 2: Bad sleep nights
Barrier 3: Kid chaos
```

The clustering uses the existing LLM client. Updated weekly (don't churn labels day-to-day).

### Phase 3 (Coach-authored): Marcus picks

The LLM (with voice spec applied) picks the three most useful labels for *this user, this month* — could be from friction notes, from the past-failure question (Q8), or from observed patterns (consecutive miss days). The phrasing follows the older-brother voice register: short, declarative, specific.

Ship Phase 1 with the prototype. Phase 2 comes after first real users log friction. Phase 3 once we have the voice pipeline running on real data.

## Animation model

**Pacing:** slow and contemplative. Apple Activity Ring vibe, not confetti cannon. The user should be able to *sit and watch this* without feeling assaulted by motion.

Concrete parameters:
- Pellet drop rate: **1 per second**, deterministic from a seeded RNG
- Pellet speed: **2.5 sec to fall the full hero height** (slow — most apps would make this 0.8s)
- Pellet diameter: 8pt
- Stray-pellet leak rate when barrier inactive: **30%** of pellets at that y-coordinate
- Barrier "flash" duration when an intervention just fired: 1.2s — ember pulse, not red strobe

**Pellet color:** ember gradient (matching Theme.emberGradient). Why ember and not white (like Strawberry)? Because *every pellet is a session being protected* — it should read warmer, not neutral. Subtle but important: Strawberry pellets feel like "potential lost"; ours feel like "energy spent on you."

**Cup fill animation:**
- Cup capacity is the *visible* votes count — the cup gets fuller as the user accumulates votes
- Pellets that "land" in the cup animate from the bottom of the hero to settle into the pile
- When cup is full (e.g. 100 votes), pellets compact slightly so it doesn't overflow off-screen
- Empty cup state (votes = 0): a single small pellet drops, animation continues but cup stays mostly empty

**Reduce motion:**
- Respect `@Environment(\.accessibilityReduceMotion)`. When on, render a static composition: funnel + 3 barriers + cup with current votes. No animation.

## State transitions

| User state | What the user sees |
|---|---|
| Day 0 (just completed intake, 0 votes) | Empty cup. Pellets just starting to fall. Generic labels. Barriers all active (we promise the future). |
| Day 5 (3-4 votes) | Cup has a few pellets. Generic labels still. Barriers active, occasional flash when a slip was caught. |
| Day 30 (20-30 votes) | Cup half-full. Personalized labels from the user's friction notes. Barriers active 5+ days/week. |
| Slip-day intervention firing | One barrier flashes ember; the pellet that would have leaked instead bounces off and continues down. |
| Pause state | Pellet flow slows to ~1 per 5s. The funnel narrows visually. Voice on Coach tab still says "paused." |
| Return after absence | Pellet flow resumes at normal rate. The cup count doesn't reset — your votes accumulated. |

## Build phases

### Phase A — Static prototype (4-6 hours)

Goal: see the visual on screen, validate the spatial design before committing to animation.

- Replace `SummitHero` view in Becoming tab with a new `PelletFlowHero` view
- Static rendering with `Canvas` — funnel, 3 barriers, cup, ~30 pellets in fixed positions
- Generic labels hardcoded
- Cup fill bound to `world.votes_cast`
- No animation yet
- Ships behind a feature flag so we can A/B against the old mountain

### Phase B — Ambient animation (6-8 hours)

Goal: pellets actually falling, looks alive.

- `TimelineView(.animation)` wrapping the Canvas
- Pellet positions computed from `t = timeline.date.timeIntervalSince(start)`
- Pellets occupy a stable seeded path each (so they're consistent within a session)
- Barriers visually catch or pass pellets based on a hardcoded "all active" state
- Reduce-motion handling
- Cup fills as votes count grows (animated)

### Phase C — Data integration (4-6 hours)

Goal: barriers reflect real intervention history.

- Backend: new field on `CoachState.recent_interventions: [str]` (or query existing nudge/journal data)
- iOS: pass intervention list to PelletFlowHero
- Barriers activate/deactivate based on intervention recency
- Subtle flash when a new intervention fires (via the existing `coachStateChanged` notification)

### Phase D — Personalized friction labels (3-4 hours)

Goal: labels reflect the user's actual patterns.

- Backend: new endpoint `GET /friction/top-three` returning 3 short labels (LLM-clustered from reports)
- iOS: fetch on Becoming tab open; cache for 24h
- Falls back to generic three if backend returns fewer

Total: roughly **2-3 days of focused work to ship Phases A-D** for one user. Probably another 1-2 days of polish.

## Open questions

1. **Replace mountain entirely, or render it behind the pellet flow?** Recommendation: replace for v1, evaluate after 1 week of usage.
2. **Tappable barriers?** Tapping "Tue work crunch" could open a sheet listing every Tuesday the coach intervened. Compelling but adds scope; **defer to v2.x**.
3. **Should the pellet flow appear in the weekly letter as a static export?** Probably yes, eventually — but only after the live version is shipped and stable. Static export = render Canvas → PNG → embed.
4. **Particle physics or simulated paths?** Simulated paths (deterministic, performant) for v1. Real physics (collisions, gravity) is over-engineering. The simulation looks "physical enough."
5. **Mobile data / battery:** the animation runs only when the Becoming tab is visible (SwiftUI handles `onAppear`/`onDisappear`). Negligible cost.
6. **Should pellets that leak past inactive barriers be *labeled* (e.g. "missed Tuesday")?** Probably not at v1 — too much information density. The presence of leaks is itself the signal.

## Honest risks

- **Visual fatigue.** Animation novelty wears off in ~2 weeks. Mitigation: keep it slow + low-contrast in the background. The pellet flow should feel like watching dust motes in sunlight, not like a screensaver demanding attention. After fatigue sets in, the *data values* (label personalization, intervention counts) are what keeps the user looking — not the motion.
- **Personalization misfire.** If we name a friction "After-work crashes" and the user thinks "that's not me," it feels intrusive. Mitigation: never use definitive language ("you struggle with X"). Labels are neutral patterns ("After-work crashes" reads as a *category*, not an accusation). Phase 2 only fires when we have ≥5 friction reports — small but real evidence.
- **Strawberry comparison.** Anyone who's seen the Strawberry ad will spot the inspiration. Mitigation: different orientation (ours is vertical full-screen, theirs is split-screen with text on top), different color palette (ember on coal, not white on black), different *frame* (theirs is "with vs. without coach"; ours is "the coach already at work"). Far enough away.
- **Performance.** ~50 active particles + 3 barrier shapes + canvas redraw at 60fps. Tested pattern from `StarsLayer` proves this is fine on iPhone. Watch out: don't go above ~100 particles, don't use offscreen redraws.
- **Brand muddiness.** Two competing metaphors (mountain + pellets) could confuse if both appear in v1. Mitigation: pellet flow on Becoming tab, mountain on app icon + Welcome only. Clear domains.

## Why this is worth building

The Coach's differentiator (from the earlier feedback synthesis) is that **we don't quit when the user slips, and we actively intervene where other apps just nag**. Saying that in marketing copy is easy. Showing it visually, with the user's own data, on a screen they look at daily — that's the screenshot that converts a curious tester into a loyal user.

The mountain hero says *"you're climbing."* The pellet flow says *"and here's exactly how I'm helping."* The second sentence is the product.

## What I'd want from you before coding

Three decisions to lock before I touch SwiftUI:

1. **Replace mountain on Becoming, yes/no?** (recommended yes, but real call)
2. **Phase A only, or commit to Phases A-B together?** (A is the cheapest prototype; A+B is what makes it feel alive — same animation pattern as the existing StarsLayer, so the marginal cost is small)
3. **The three generic labels** for Phase 1 — *"Schedule conflicts / Tired days / Lost momentum"* or different phrasing? These get seen by every user for their first ~5 sessions; the copy matters.

Once those three are answered, I can spike Phase A by tonight and Phase B over a couple more hours tomorrow.
