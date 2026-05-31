# 05 — Intake (v2) — GOAL-FIRST

The intake is now a **branching tree**, not a flat list. Q1 is the goal. The goal picks one of 5 templates (see [`../templates/`](../templates/README.md)). The template's intake branch determines which subsequent questions get asked.

Length varies by template: longevity → 7 questions; strength → 9; hypertrophy with focus muscles → 10; discipline with cycle picker → 11.

## Role

Same as v1: bootstrap the coach with enough about the user that the persona can derive a real program. **What's new in v2** is twofold:

1. **Goal-first (Q1)** — the missing question from v1. The user's goal determines the program template, which determines everything else.
2. **Past-failure question** — the unique-to-AI question that no tracker can use, surfaced near the end (replaces Q8 of the earlier v2 draft).

## The intake tree

```
Q1. GOAL  ────────────────────────────────────────────┐
  ├─ Build muscle      → Hypertrophy branch (10 Qs)   │
  ├─ Get stronger      → Strength branch    (9 Qs)    │
  ├─ Lose weight       → Conditioning branch (9 Qs)   │
  ├─ Stay fit, age well → Longevity branch  (7 Qs)    │
  └─ 75-Hard discipline → Discipline branch (11 Qs)   │
                                                       │
       (each branch ends with a shared closing) ←──────┘

SHARED CLOSING (every template):
  - Anchor habit
  - Location
  - What killed your last attempt? (the past-failure question)
  - Identity statement
```

The shared closing is consistent across templates. The middle (per-template) section adapts.

## The Q1 — goal selection

```
┌─────────────────────────────┐
│ < Back        1 of ?        │  ← step counter doesn't claim
├─────────────────────────────┤     a total until goal picked
│                             │
│ What do you want to do?     │  ← serif title
│                             │
│ Pick the one that fits      │  ← coach-voice subtitle
│ best. You can change later. │
│                             │
│  ○  Build muscle             │  ← single-select rows
│     Look bigger. Fill out    │     each row: short label
│     a t-shirt.               │     + one-line description
│                             │     in coach voice
│  ●  Get stronger             │
│     Move more weight.        │
│                             │
│  ○  Lose weight, get fit     │
│     Drop fat, feel better.   │
│                             │
│  ○  Stay fit, age well       │
│     Maintain. Don't get      │
│     injured.                 │
│                             │
│  ○  75-Hard-style discipline │
│     Strict, daily, photos.   │
│                             │
├─────────────────────────────┤
│ ▓░░░░░░░░░░░░░░░░░░░░░░░     │
│ [        Continue       ]   │
└─────────────────────────────┘
```

The "you can change later" subtitle matters — it lowers commitment anxiety for users uncertain about which goal fits.

Selecting a goal commits the user to that template's intake branch. Going back to Q1 to change goal resets all subsequent answers.

## Per-template question lists

### If GOAL = "Build muscle" (Hypertrophy)

| # | Question | Source |
|---|---|---|
| 1 | Goal | shared |
| 2 | Experience | hypertrophy-specific (asks novice/intermediate/advanced) |
| 3 | Days per week (3-6) | hypertrophy-specific (wider range than strength) |
| 4 | Time per session | shared time-Q |
| 5 | Focus muscle groups (pick up to 3) | hypertrophy-only |
| 6 | Injuries | shared |
| 7 | Equipment | shared |
| 8 | Baseline lifts (optional) | hypertrophy-specific |
| 9 | Anchor habit | shared closing |
| 10 | Location | shared closing |
| 11 | Past failure | shared closing |
| 12 | Identity | shared closing |

(Eleven if user skips baseline lifts, twelve if they fill it.)

### If GOAL = "Get stronger" (Strength)

| # | Question | Source |
|---|---|---|
| 1 | Goal | shared |
| 2 | Experience | shared |
| 3 | Days per week (2-4) | strength-specific |
| 4 | Time per session | shared |
| 5 | Injuries | shared |
| 6 | Equipment | shared |
| 7 | Baseline lifts (squat + bench) | strength-specific |
| 8 | Anchor habit | shared closing |
| 9 | Location | shared closing |
| 10 | Past failure | shared closing |
| 11 | Identity | shared closing |

### If GOAL = "Lose weight, get fit" (Conditioning)

| # | Question | Source |
|---|---|---|
| 1 | Goal | shared |
| 2 | Experience | shared (broader — many conditioning users haven't lifted) |
| 3 | Days per week (3-5) | conditioning-specific |
| 4 | Time per session | shared |
| 5 | Current weight / target weight (optional) | conditioning-specific |
| 6 | Conditioning preference (run/bike/swim/walk/mixed) | conditioning-specific |
| 7 | Injuries | shared |
| 8 | Equipment | shared |
| 9 | Anchor habit | shared closing |
| 10 | Location | shared closing |
| 11 | Past failure | shared closing |
| 12 | Identity | shared closing |

### If GOAL = "Stay fit, age well" (Longevity)

| # | Question | Source |
|---|---|---|
| 1 | Goal | shared |
| 2 | Age band (under 50 / 50s / 60s / 70+) | longevity-specific |
| 3 | Days per week (2-3) | longevity-specific |
| 4 | Mobility limits | longevity-specific (replaces generic "injuries") |
| 5 | Equipment (plain-English options) | longevity-flavored |
| 6 | Anchor habit | shared closing |
| 7 | Location | shared closing |
| 8 | Past failure | shared closing |
| 9 | Identity | shared closing |

Shortest branch. No baseline lifts, no time-per-session (default is 30 min — short by design), no focus muscles.

### If GOAL = "75-Hard-style discipline" (Discipline)

| # | Question | Source |
|---|---|---|
| 1 | Goal | shared |
| 2 | **Cycle picker (75 classic / 75 soft / 30 starter / open)** | discipline-specific |
| 3 | Days per week (6 or 7) | discipline-specific |
| 4 | AM/PM split or single? | discipline-specific |
| 5 | Photo time | discipline-specific |
| 6 | Contract items (water? reading? outdoor?) | discipline-specific |
| 7 | Have you done a strict program before? | discipline-specific (soft-gate) |
| 8 | Injuries | shared |
| 9 | Equipment | shared |
| 10 | Anchor habit | shared closing |
| 11 | Location | shared closing |
| 12 | Past failure | shared closing |
| 13 | Identity | shared closing |

Longest branch. The cycle picker + contract items are the discipline-specific surface area.

## What the user sees at the bottom of the screen

The progress bar adapts: once the user picks a goal, the total step count updates. Pre-goal selection, the counter says "1 of ?" — honest about not knowing yet.

After goal selection: "2 of 11" (strength), "2 of 13" (discipline), etc. The counter tells the user how much further to go.

## The 9 (or 11, or 13) questions — what changed from v1

| | v1 | v2 |
|---|---|---|
| Question count | 8 (flat) | 7–13 (goal-dependent) |
| Q1 | Experience | **Goal** |
| Q1 back chevron | Disabled | **Enabled** — user can back out |
| Q3 skip pill text | "Nothing — I'm good" | **"All clear"** |
| Q5 unsure UX | Switch | Preserved |
| Past-failure question (new) | — | Added (varies position by template, always near end) |
| Identity copy | "Who are you becoming? One sentence. This becomes your summit." | Preserved with one new line: *"Tell me like you'd tell a friend."* |
| Welcome tagline | "A copilot that pushes when it matters…" | "A coach who notices when you slip. And is still here when you come back." |
| Submitting copy | "Building your program" | "Putting your **{goal}** program together. One minute." (template-aware) |
| Continue button label | "Continue" / "Build my program" | Same final label, but penultimate uses **"Almost done"** |

## What changed from v1

| | v1 | v2 |
|---|---|---|
| Question count | 8 | 9 |
| Q1 back chevron | Disabled | **Enabled** — user can back all the way out |
| Q3 skip pill text | "Nothing — I'm good" | **"All clear"** |
| Q5 unsure UX | Switch | Preserved |
| Q8 (new) | — | **"What killed your last attempt?"** |
| Q9 (old Q8) identity copy | "Who are you becoming? One sentence. This becomes your summit." | Preserved with one new line: *"Tell me like you'd tell a friend."* |
| Welcome tagline | "A copilot that pushes when it matters…" | "A coach who notices when you slip. And is still here when you come back." |
| Submitting copy | "Building your program" | "Putting your program together. One minute." |
| Continue button label | "Continue" / "Build my program" | Same final label, but penultimate (Q8) uses **"Almost done"** |

## Wireframe — Q8 (the new one)

```
┌─────────────────────────────┐
│ < Back        8 of 9        │
├─────────────────────────────┤
│                             │
│ What killed your last       │  ← serif title (big)
│ attempt?                    │
│                             │
│ Honest answers help me      │  ← subtitle in coach voice
│ pre-empt the same thing.    │
│                             │
│ ┌─────────────────────────┐ │
│ │ Tell me what happened…  │ │  ← multi-line text field
│ │                         │ │
│ │                         │ │
│ │                         │ │
│ └─────────────────────────┘ │
│                             │
│ Or pick one:                │  ← carousel of examples
│                             │
│ [· work got busy         ·] │  ← tap to populate field
│ [· lost motivation       ·]
│ [· injury                ·] │
│ [· life changes          ·] │
│ [· first time trying     ·] │  ← for users with no history
│                             │
├─────────────────────────────┤
│ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░          │
│ [        Almost done    ]   │  ← CTA labeled penultimately
└─────────────────────────────┘
```

**Behavior:**
- Free text input is the primary affordance.
- Tapping a carousel chip populates the text field with that phrase. The user can keep typing to add detail.
- "First time trying" populates with that string and is a valid answer — for users who haven't failed at this before. The brain treats it differently in adaptation (no specific failure pattern to pre-empt; instead, treats the user as high-risk for the most common dropout patterns: week-3 motivation drop).

**Why it lives just before identity:**

Atomic Habits frames identity as built from evidence. If we ask the identity statement *first*, the user writes an aspirational lie ("I want to be incredibly strong and disciplined"). If we ask the failure pattern *first*, the user comes to the identity question with their actual self in mind. The statement they write afterward is more grounded — closer to who they *can* be, with the failure pattern named.

Concretely: a user who answers Q8 with *"I lost motivation around week 3, kept saying I'd start again"* is much more likely to write Q9 as *"someone who finishes what they start"* than *"a world-class athlete."* The former is what the coach can actually deliver on.

## Where the answer flows downstream

The Q8 answer is stored as a structured field and threaded through:

1. **Initial program design** — the persona considers the failure pattern when picking the schedule. A user who failed on intensity gets a slower ramp.
2. **Adaptation context** — the LLM that generates nudges and the weekly letter has access to this answer in its system context. When the user is on day 14 (the historical fail-point), the brain knows to be more attentive.
3. **Shape C (slip-day) phrasing** — when the user slips, the LLM can reference the named pattern. Example planner intent for Shape C, with Q8 = "work got busy":
   > *"Marcus knows: when work gets busy, this user stops. Two missed sessions match the pattern. Today's intervention should acknowledge work as the likely cause without asking — open with a sharper-than-base question."*

## Other v2 intake changes

### Welcome screen

```
┌─────────────────────────────┐
│                             │
│            ⛰                │
│                             │
│       The Coach             │
│                             │
│   A coach who notices       │  ← NEW tagline
│   when you slip.            │
│   And is still here when    │
│   you come back.            │
│                             │
│   [    Get started     ]    │
│                             │
│   Five minutes. Mostly      │  ← NEW CTA caption
│   questions. Like meeting   │     replaces v1's
│   a new trainer.            │     "about a minute"
│                             │
└─────────────────────────────┘
```

The "five minutes" is honest — Q8 adds time and we want the user to settle in. The "like meeting a new trainer" framing primes the right mental model.

### Submitting screen

```
        ⛰ (spinning)
        
   Putting your program
   together. One minute.
```

Same animation. Cleaner, in-voice copy.

### Failure state

If submission fails twice:

```
   ⚠
   
   Something's not working.
   Try again in a minute.
   
   [    Try again    ]
```

No "we're so sorry!", no "our team has been notified." Marcus voice — short, honest, no theater.

### Back-out from Q1

v1 disabled the back chevron on Q1. v2 enables it. Tapping it returns to the Welcome screen with all answers preserved as drafts (held in SessionStore, not yet submitted). The user can resume by tapping "Get started" again. Persistence of intake drafts is a small but important UX win — we don't punish a user who got interrupted partway through.

## Validation rules per question

These haven't changed conceptually from v1 — listed for completeness:

- Q1, Q2, Q4: always valid (no empty state possible)
- Q3: non-empty required (or skip pill tapped — "All clear" populates the field with `"none"`)
- Q5: either a number > 0, or "unsure" switch on
- Q6, Q7, Q8, Q9: non-empty required, ≥3 characters, no profanity (server-side LLM check — keep it light, no aggressive filter)

## Why we kept it as 9 structured questions and not a free LLM interview

The spec frames intake as a conversation, not a form. v1 relaxed that for HIG-native pickers; v2 keeps that relaxation. Reasons:

1. **Predictable program output.** A structured intake produces structured input, which produces a more reliable program. An LLM interview can drift.
2. **Time honesty.** 9 questions in 5 minutes is faster than an open-ended chat. The "meeting a new trainer" framing makes the form-shape feel right.
3. **User-pickable carousel chips.** A free-text-only Q8 would be intimidating. Chips give the user a starting point.

The spec's "conversation, not form" ideal is preserved in **how the questions are worded** (direct, second-person, coach voice) rather than **how the input is collected**. We get the best of both.

## Risks

- **Q8 may feel intrusive on day 0.** "What killed your last attempt?" is heavier than the practical questions before it. The placement matters. We placed it after the practical questions are answered (so the user has already invested 5 minutes and feels committed) but before identity (so identity is grounded). If users abandon at Q8 in testing, we'll consider moving it to after the program is built — as a "tell me what to watch out for" check-in surface instead.
- **Lying on Q8.** Some users will write something flattering or vague to avoid the question. The brain can detect very short or evasive answers and either (a) accept and treat as "first time" (default to high vigilance), or (b) gently re-ask later. We won't push harder than that. Coaches don't.
- **The "First time trying" chip.** Users who select this could be either truly new or just defensive. We treat them identically: high vigilance on the historical fail-points (week 1 attendance, week 3 motivation drop, week 6 plateau). Generic but reasonable.

## Open questions

- Should we add a Q10 about preferred contact time (e.g. "When's the best time to hear from me?") to seed the JITAI timing? Probably not for v2 — calendar gaps + HealthKit already drive timing. Adding it would lengthen intake and the brain can learn the right time from response patterns. Maybe v2.1.
- Should Q9 (identity) have an example carousel like Q8? **Probably no** — examples there would anchor the user to common-shape answers and dilute the personal statement. Q8 wants normalization (you're not alone); Q9 wants singularity.
