# Composable blocks — architecture for a dynamic app

A pivot in how we think about the app's surface. The v2 design we just wrote is *one composition* of a smaller, controlled set of building blocks. Most users will get that default composition (Marcus's preferred shape). But the architecture should let us — and eventually the brain — assemble different compositions for different users without rebuilding the app.

This is the LLM-as-UI-composer pattern: the brain doesn't just decide *what to say*, it also decides *what to show*, picking from a palette we control.

> Quick caveat: I haven't pinned down what "Wysi" specifically refers to. The concept the user described — controlled block palette, LLM-driven composition — maps to what's often called "generative UI" or "agent-composed interface." I'll use those terms generically here; substitute the correct reference if needed.

---

## The problem with one fixed workflow

The v2 design assumes every user wants Marcus's default arrangement: 3 tabs, Coach as front door, weekly letter on Sunday, no photos, no macros, no water tracking. That's a good default — calibrated for the dropout-prone strength-training user. But it's not universal:

- A **75 Hard-adjacent user** wants daily photo accountability, water intake, and a stricter coach voice.
- A **hybrid endurance + strength user** wants cardio segments and a different prescription shape.
- A **macro-focused recomp user** wants nutrition logging alongside lifting.
- A **busy professional** wants only Sunday check-ins and silence the rest of the week.
- A **person who likes pen-and-paper journaling** wants a free-text reflection block.
- A **return-from-injury user** wants daily symptom check-ins.

If we ship one fixed workflow, we either:
1. Pick one user type and lose the rest (current v2 default targets the dropout-prone strength user)
2. Bloat the default with every feature (becomes a tracker — the failure mode)

The composable architecture says: **define the blocks once, let composition vary by user.**

---

## The principle

| | |
|---|---|
| **We control the blocks.** | The user does not author UI. They cannot draw shapes or write CSS. They pick from a curated palette of ~20 blocks we've designed, tested, and voiced. |
| **The brain composes.** | The user does not arrange blocks manually. The LLM brain composes a layout based on user preferences + observed behavior. Users describe what they want in natural language; the brain assembles. |
| **Defaults always exist.** | A new user gets the Marcus default composition. They never see a blank canvas. Composition is opt-in, never forced. |
| **The voice spec still gates strings.** | Any string in any block, in any composition, still goes through the voice transformer. The composition can vary; the voice doesn't. |
| **The brain has hard rules.** | Certain blocks MUST appear under certain conditions (e.g. slip-intervention block on day 3 of a slip, regardless of user preferences). The brain composes within product-defined invariants. |

This is **constrained generative UI**, not freeform. We keep the cohesion guarantees of designed software while gaining the flexibility of LLM composition.

---

## The block taxonomy

Three categories of block: **core, optional, escalation**.

### Core blocks (always in the palette; default user sees a subset)

These ship in v2 because the v2 fixed workflow uses them.

| Block | What it does | Default users see it? |
|---|---|---|
| `CoachVoiceCard` | The ember-tinted "from your coach" body | Yes |
| `PrescriptionPeekCTA` | "Show me the session" button | Yes |
| `ExerciseList` | The lift-by-lift breakdown | Yes |
| `TheScriptCard` | Cue → action → location implementation intention | Yes |
| `LogSessionCTA` | Primary "log this session" button | Yes |
| `MinimumDoseCard` | Bad-day affordance with the 2-set fallback | Yes (conditional) |
| `FrictionReportPrompt` | The slip-day tag-picker for what's getting in the way | Yes (in Shape C only) |
| `IdentityRestatement` | The user's identity statement in coach voice | Yes |
| `VotesCard` | The big number — votes cast | Yes |
| `MountainHero` | The growing summit visualization | Yes |
| `MilestonesList` | Waypoints, achieved + pending | Yes |
| `LivingSystemCard` | Habit vitality ring + coach read | Yes |
| `ThisWeekGrid` | 7-day session strip | Yes |
| `FollowupCard` | Owed-reply amber card | Yes (when relevant) |
| `WeeklyLetter` | Sunday narrative full-screen | Yes |
| `PauseAck` | Coach-silent acknowledgment | Yes (when paused) |
| `ReturnPrompt` | "Haven't seen you in a bit. Still in?" | Yes (when absent 5d+) |

### Optional blocks (in the palette; default users don't see them — power users opt in)

These don't ship UI in v2, but the **block contracts are defined** so future implementation slots in cleanly.

| Block | What it does | Who'd want it |
|---|---|---|
| `PhotoCheckIn` | Daily photo upload, calendar grid view | 75 Hard-shaped users, transformation-tracking users |
| `MacroLog` | Protein / carbs / fat tally with coach commentary | Recomp users |
| `SleepCard` | HealthKit sleep summary + coach read on it | Users who want sleep accountability |
| `CardioSegment` | Distance/duration log inserted into prescription | Hybrid / endurance users |
| `WaterIntake` | Oz/L tracker with bar | Users who actually care (most don't) |
| `WeightLog` | Body weight tracking with trend line | Recomp / cut / bulk users |
| `VoiceMemoToCoach` | Voice reply to nudges; transcribed server-side | Users who don't want to type |
| `JournalReflection` | Free-text journal block tied to the session | Pen-and-paper-style users |
| `PublicCommitment` | Share a session completion to a connected feed | Accountability-via-social users |
| `BuddyCheck` | Connect with one accountability partner; see their day | Accountability-via-pair users |
| `MoodCheckIn` | Pre-session 1-tap mood rating | Mind-body users; users tracking mental health correlation |
| `SymptomTracker` | Pain/discomfort daily log | Return-from-injury users |

### Escalation blocks (the brain inserts these regardless of user prefs)

Some blocks are **non-negotiable** — the product enforces them when state requires it, overriding user customization. These keep the safety and the moat intact.

| Block | When it appears | Why mandatory |
|---|---|---|
| `SlipIntervention` | 2+ consecutive misses | The differentiating surface — must work for every user |
| `ReturnPrompt` | 5+ days absent | Same |
| `SafetyHandoff` | User reports pain/injury/mental-health content | Spec §4.4 — the coach refers, not diagnoses |
| `BackendErrorState` | Connectivity / API failures | Honest failure rendering |

A user who configured a "silent, only-Sunday" composition will *still* see the slip intervention on day 3 of a slip. That's the moat clause: customization can't disable the thing that makes us different.

---

## How a block is defined

A block is a self-contained unit with five properties:

```yaml
block:
  id: PhotoCheckIn
  
  # The data this block reads from the brain
  data_binding:
    - source: world.photos
      shape: list[Photo]
    - source: user.preferences.photo_required_daily
      shape: bool
  
  # The voice surfaces this block may emit (each runs through the voice transformer)
  voice_surfaces:
    - id: photo_streak_compliment
      trigger: 7+ consecutive days uploaded
      planner_intent: {purpose: "compliment streak"}
    - id: photo_missed_yesterday
      trigger: no upload for 24h+ when preference says daily
      planner_intent: {purpose: "nudge missed photo"}
  
  # When this block is allowed to be in the layout
  appearance_rules:
    - user_must_have_opted_in: true
    - hidden_when: brain.surface == "slip-intervention"  # don't compete with escalation
  
  # The interaction(s) this block exposes
  interactions:
    - tap_upload: opens camera
    - long_press_calendar: shows grid view
  
  # Where in the tab structure this block can live
  placement_slots:
    - tab: coach
      position: below_main_card
    - tab: becoming
      position: bottom_section
```

A block is **not a SwiftUI view**. It's a *contract*. The iOS implementation provides the view that satisfies the contract. The brain reads contracts to know what's available, what data each block needs, and where each block can live.

This is the layer that lets the brain compose.

---

## How composition works

Composition is a **constrained problem** the brain solves:

```
input:
  - user.preferences (what blocks they've opted into)
  - user.state (training, slipping, paused, etc.)
  - calendar context (Sunday letter time? quiet hours?)
  - block contracts (what's in the palette)

output:
  - per-tab layout: ordered list of block IDs to render
  - per-block intent objects (planner output for each voice surface)
```

The brain doesn't draw the UI. The iOS app draws blocks. The brain just answers: *given this state and these preferences, which blocks go where?*

### Example: default Marcus composition

```yaml
coach_tab:
  - shape: ShapeB  # the active shape (composed of multiple blocks)
    blocks:
      - CoachVoiceCard
      - PrescriptionPeekCTA
      - FollowupCard  # if owed
  
now_tab:
  - TheScriptCard
  - SessionHeader
  - ExerciseList
  - ProgressionRule
  - LogSessionCTA
  - MinimumDoseCard  # conditional

becoming_tab:
  - IdentityRestatement
  - VotesCard
  - MountainHero
  - StatsStrip
  - MilestonesList
  - LivingSystemCard
  - ThisWeekGrid
```

### Example: 75 Hard-shaped composition (hypothetical user)

```yaml
coach_tab:
  - shape: ShapeB
    blocks:
      - CoachVoiceCard  # voice can be sharper for this user — see below
      - PrescriptionPeekCTA
      - PhotoCheckIn  # opted in
      - WaterIntake  # opted in
  
now_tab:
  - TheScriptCard
  - SessionHeader
  - ExerciseList
  - PhotoCheckIn  # also here
  - LogSessionCTA

becoming_tab:
  - IdentityRestatement
  - VotesCard
  - MountainHero
  - ThisWeekGrid  # photo-grid version
  - MilestonesList
```

Same blocks, different composition.

### Example: minimalist user (weekly check-in only)

```yaml
coach_tab:
  - shape: ShapeMinimal  # custom shape — Sunday letter only, nothing else
    blocks:
      - WeeklyLetter

now_tab:
  - WeeklyPrescription  # different rendering — week-at-a-glance

becoming_tab:
  - VotesCard
  - MilestonesList
```

---

## How users configure their composition

Three layers, in increasing flexibility:

### Layer 1 — Onboarding shape picker (v2.1)

A 10th intake question, after identity:

> *"How should I show up for you?"*
>
> ○ Daily — push when an opportunity opens *(default — Marcus shape)*
> ○ Weekly — Sunday check-in only
> ○ Strict — daily photos and full accountability *(75 Hard shape)*
> ○ Hybrid — strength + cardio
> ○ Let me figure it out later

Each option maps to a pre-defined composition that we've tested. The user is picking from **shapes we've designed**, not blocks. Lower cognitive load, lower risk of bad compositions.

### Layer 2 — Settings → "Tune my coach" (v2.2)

For users who want to adjust:

> *"What should I add?"*
>
> [+] Photo check-ins
> [+] Macro logging
> [+] Sleep tracking
> [+] Voice memos
> [+] Cardio segments
>
> *"What should I remove?"*
>
> [−] Milestones tab
> [−] Mountain visualization
> [−] Weekly letter

Each toggle adds/removes a block from the user's composition. The brain recomposes the next time the app refreshes. The user sees the change immediately.

### Layer 3 — Chat with the coach (v3)

The full agent composition. The user just *talks*:

> User: "I want photo accountability but only on lift days, and I don't care about the mountain visualization."

The brain interprets:
- adds `PhotoCheckIn` block with conditional trigger (lift days only)
- removes `MountainHero` from the Becoming tab
- replies in Marcus voice: *"Done. Photos start Tuesday. Mountain's gone."*

This is the LLM-as-composer layer. Risky to ship blind — needs heavy testing — but it's where the architecture eventually leads. A user can literally redesign their app surface by talking to the coach.

---

## v2 scope: ship fixed, architect for flex

The architecture above is a v3 endpoint. For v2 we do this:

| | v2 | v2.1 | v2.2 | v3 |
|---|---|---|---|---|
| Block-shaped engineering | ✅ ship | — | — | — |
| Default composition (Marcus) | ✅ only option | ✅ | ✅ | ✅ |
| 5-block optional palette implemented | ❌ contracts only | ✅ photo, macro | ✅ + sleep, voice memo | ✅ all |
| Onboarding shape picker | ❌ | ✅ | ✅ | ✅ |
| Settings tune-my-coach | ❌ | ❌ | ✅ | ✅ |
| Chat-with-coach composition | ❌ | ❌ | ❌ | ✅ |

**The cost in v2:** engineering implements every block as a discrete unit with a clean data binding and contract, even though only one composition ships. This is more work than building screens directly — maybe 20–30% overhead. **Worth it.** The alternative is rebuilding the whole iOS app at v2.2 when composability lands.

**The benefit:** when v2.1 ships the shape picker, no engineering rework is needed on the existing blocks. They're already composable. We just add a new arrangement.

---

## How the brain knows what to compose

The brain reads:

1. **The block manifest** — a YAML file (or DB table) describing every block contract. Single source of truth, generated from the iOS app's block registry at build time. The brain doesn't guess; it knows what's available.
2. **The user's preferences** — composition prefs persisted server-side.
3. **The user's state** — current shape (Quiet/Prescription/Slip/Return/Pause-ack), recent events, calendar.
4. **The product invariants** — escalation blocks that must appear under specific conditions, overriding user prefs.

Composition is an LLM call:

```
SYSTEM:
  You compose mobile app layouts from a controlled block palette.
  The user is a {persona snapshot}. They've configured: {prefs}.
  Their current state: {state}.
  
  Available blocks: {manifest}.
  Invariants: {escalation rules}.
  
  Output a JSON layout per tab. Use only blocks in the manifest.
  Include voice intents for any block requiring coach speech.

USER:
  Compose the layout for {tab} right now.
```

The output is parsed by the iOS app, which then renders the blocks in order. Each block's voice surfaces run through the voice transformer separately.

> **Caching:** layouts shouldn't recompose every app open. They recompose on (a) state change, (b) preference change, (c) explicit refresh. Otherwise they're cached for the day. This keeps generation cost low and behavior predictable for the user (the app doesn't feel like it's morphing randomly).

---

## The risks

This architecture has real costs. Naming them honestly:

### Cohesion risk

**The more compositions are possible, the more chances we ship a broken-feeling combination.** Mitigation: ship only **tested** compositions in v2.1 (shape picker — 5 pre-defined shapes, not free composition). Free composition (v3) only unlocks when we have telemetry showing user-composed layouts feel as good as pre-tested ones.

### Brand voice risk

**Optional blocks like PhotoCheckIn might come from a different design tradition (75 Hard) and clash with Marcus.** Mitigation: every block, even optional ones, must pass the voice spec. A photo upload block doesn't get a "log your gainz!" CTA — it gets a quiet "today's photo" prompt and a coach line in Marcus voice. The voice unifies even when blocks differ.

### Implementation complexity risk

**Composable UI is significantly more complex than fixed SwiftUI screens.** Real cost: ~30% engineering overhead in v2, possibly more. Mitigation: define block contracts simply (data + voice + placement); resist the urge to make blocks themselves over-flexible (each block is rigid internally, composition happens at the layout level only).

### LLM composition risk

**Letting the brain choose layouts means the brain can choose badly.** A user might open the app and find their familiar layout has been rearranged because the brain decided. Mitigation: layouts recompose only on user-initiated triggers (preference change, explicit "refresh my coach" command) — not silently on every app open. Stability is part of the contract.

### Decision-paralysis risk

**"Configure your own app" is the exact thing that kills new users in onboarding.** Mitigation: the default composition is *always* the Marcus shape. Configuration is opt-in, surfaced via Settings, never required during intake. A user who never opens Settings gets the same v2 we just designed.

### Eval risk

**With 5 tested compositions and 12 optional blocks, the combinatorial space of possible user-facing surfaces is large.** We can't manually QA every combination. Mitigation: per-block visual tests + per-composition end-to-end tests for the 5 shipped shapes + property-based tests for arbitrary block insertions (does the tab still render with this block added?).

### The "ChatGPT for fitness" trap

**If we lean too hard into chat-with-the-coach composition, we become a chatbot, not a coach.** Spec Principle 2: *copilot, not chatbot*. Mitigation: keep composition behind a single conversational gate ("How should I show up for you?") rather than turning the whole app into a chat. The coach is still the coach; the conversation is about *how to coach this user*, not what to do today.

---

## A note on what we're NOT building

This is composable UI for **a coach app**, not a build-your-own-app platform. The user doesn't:

- Write code
- Author new blocks
- Connect arbitrary integrations
- Style or theme the app
- Build their own features

They pick from blocks we've designed, voiced, and tested. The flexibility is in **which blocks**, not **what blocks can do**. This is the same principle that makes Notion templates work (users compose from pre-built building blocks) without turning Notion into a programming environment.

---

## Open questions

- **Should the brain be allowed to *suggest* composition changes, not just respond to user requests?** E.g. after 4 weeks of consistent training, the coach offers: *"You've been steady. Want to add cardio?"* — adding a new block to the user's composition. Probably yes (this is the spec's *initiative* principle applied to UI), but only after we've shipped manual composition and seen how users react.

- **Where does the block manifest live?** Options: (a) backend YAML file, (b) generated from iOS code at build time, (c) versioned API endpoint. Probably (c) — the iOS app ships with a block registry, and the backend has a manifest endpoint that says "here are the blocks the current iOS version supports." Version skew handling matters.

- **Can a single block have variants?** E.g. PhotoCheckIn might have a "strict" variant (must upload daily) and a "soft" variant (uploads optional). Are those one block with config, or two blocks? Probably one block with config (less palette bloat).

- **What does a "composition reset" look like?** If a user has tuned themselves into a bad place, can they say "reset to Marcus default" from Settings? Probably yes — a one-tap button to restore the shipped default.

- **What about A/B testing compositions in production?** Once the architecture is in place, we can ship two default compositions and see which retains better. This is one of the biggest payoffs of the architecture — it makes future product iteration cheap.

---

## Bottom line

Composable architecture is the right v3 endpoint. **In v2, we ship the fixed Marcus default but architect every screen as composed of blocks.** The 30% engineering overhead in v2 buys us the ability to ship 5 pre-tested compositions in v2.1, custom toggles in v2.2, and a true LLM-composed app in v3 — without rebuilding.

The bet: the differentiation that lets us win the dropout-prone segment in v2 (Marcus + slip-intervention + return path) earns us the user base; v2.1/v2.2/v3 composability lets us expand into adjacent segments (75 Hard, hybrid, minimalist, recomp) without diluting the core voice or rebuilding the app.

If we don't architect for blocks in v2 and try to add composability in v2.2, it's a full rebuild. If we do architect for blocks now, every later feature ships as a block addition. The compounding here is large.

## What this changes for the v2 engineering tickets

The v2 screens documented in `screens/` should be reframed as **compositions of blocks** rather than monolithic SwiftUI views. Concretely:

- Every `View` in the iOS app should be a Block conforming to a Block protocol with `data`, `voiceSurfaces`, `placement` properties.
- The `Coach`, `Now`, `Becoming` tabs become layout containers that read a composition spec and render the listed blocks in order.
- The composition spec comes from the backend (`GET /composition?tab=coach`) and is cached per-day.
- The default composition (Marcus shape) is hardcoded for v2 launch.

That's the architecture diff for engineering. The screens still look exactly like the wireframes in `screens/01-coach-tab.md` etc. — they're just *built differently underneath*.
