# Template 05 — Discipline

The "75-Hard-style" goal. Strict, no-skip, photo-required, often two-a-days. The hardest segment to retain, the loudest segment to delight.

## Who picks this

The user who said *"I want strict accountability. No softness. Daily."* Concretely:

- Has done 75 Hard, possibly more than once
- Or aspires to (the "considering 75 Hard" segment is bigger than the "completed" segment)
- Sees fitness as a discipline challenge first, body composition second
- Often professionally driven — entrepreneurs, military, finance, athletes
- Wants the app to *enforce* what they've decided to do
- Hassan from the persona walkthroughs is the prototype

Anti-personas:
- Wants to "ease in" — wrong template
- Wants flexibility around life — wrong template
- Wants a 2-day program — wrong template

This is a self-selected hardcore segment. The template's failure mode is *being too soft*, not too hard. Inverse of every other template.

## The discipline contract

The template enforces a daily contract — distinct from the other templates which suggest, encourage, adapt:

1. **Two workouts per day** (or one ≥45 min for the lighter variant)
2. **At least one workout must be outdoors** (or unconditional if the user opts in)
3. **A photo every day, same time**
4. **No skipped days** — slip resets the cycle (configurable: 75-day, 30-day, or open-ended)
5. **One quart/liter of water tracked daily** (yes, water — 75 Hard's signature)
6. **One reading session per day** (10 pages — also 75 Hard tradition)

Items 1-4 are the workout/coach surface. Items 5-6 are accountability blocks the user can opt in or out of (composable-blocks architecture — see `../composable-blocks.md`).

The user picks the contract during a more elaborate goal-selection step (see "Onboarding deviation" below). Once set, the contract is what the brain measures against.

## Split structure

**6 training days/week, two-a-days allowed.**

Two workouts/day means one is usually strength/hypertrophy and the other is conditioning/cardio. Typical week:

| Day | AM | PM |
|---|---|---|
| Mon | Lift (Upper) 45 min | Run/Bike 45 min (outdoors) |
| Tue | Lift (Lower) 45 min | Conditioning/HIIT 45 min |
| Wed | Cardio (Easy) 45 min | Mobility/Recovery 45 min (outdoors) |
| Thu | Lift (Upper) 45 min | Run/Bike 45 min (outdoors) |
| Fri | Lift (Lower) 45 min | Conditioning 45 min |
| Sat | Long cardio 60 min (outdoors) | (optional) |
| Sun | Rest (active recovery walk allowed) | Photo + reading time |

Six "training days" — meaning days with at least one logged workout. Sunday is a recovery day but the photo + reading + water still count.

### Single-workout variant

For users who want strictness but not two-a-days: one ≥45 min workout per day, six days. Still photo, water, reading, etc.

This is the **"75 Soft"** variant — less common in the discipline segment but real.

## Rep ranges

This template borrows from Strength + Hypertrophy + Conditioning depending on the day:

- AM lifts (strength): 5×5 or 4×6-8 — strength-leaning
- PM conditioning: intervals, runs, circuits — varied
- Mobility: time-based

The exact session content is less load-bearing than the *cadence*. The user is here for the discipline of doing it daily; the program is secondary.

## Progression

Standard progression on the lift sessions (hypertrophy-style double progression). On cardio, distance/pace creep weekly.

**The defining progression in this template is NOT load — it's days completed.** Day 1 to Day 75 (or whatever cycle length the user picked). That's the bar.

If the user breaks the streak, the cycle **resets to day 1** by default. This is the 75 Hard cultural norm and the user picks this template *because* they want it. The brain offers to make it less strict at intake ("hard reset on miss" vs "you keep your days, you just don't get the badge"), but defaults to hard.

## Days/week supported

**Exactly 6 or 7. Less is wrong template.**

| Days | Structure |
|---|---|
| 6 | Canonical |
| 7 | Adds one easy active recovery day; for users who want absolute daily |

Below 6 → route to a different template. This template is binary about cadence.

## Time per session

- AM session: **45 min** (sometimes 30 min for the "lighter" variant)
- PM session: **45 min**
- Total daily time investment: **~90 min plus prep**

Time-per-session is asked but with a floor at 30 min. Anything less and the discipline template loses its identity.

## Equipment branches

| Equipment | What changes |
|---|---|
| Full gym | Canonical — AM lift session leverages full gym |
| Barbell+rack at home | Works; cardio happens outside |
| Dumbbells | AM lift uses DB versions; cardio outside |
| Bodyweight | Possible but harder to do strict 6-day program — discourage but allow |

## Onboarding deviation

Discipline gets a unique extra step that other templates skip: **picking the cycle**.

After goal selection, the user picks:

> *"How strict?"*
>
> ◯ **75-day classic** — 2 workouts/day, photo, water, reading. Hard reset on miss.  
> ◯ **75-day soft** — 1 workout/day, photo, water, reading. Hard reset on miss.  
> ◯ **30-day starter** — same rules, shorter horizon for first-timers.  
> ◯ **Open-ended** — daily, no reset, just streak tracking.

Each cycle option maps to slightly different session generation + tracking logic.

## Sample week — full gym, 75-day classic

```
Monday
  AM (45 min) — Upper Lift A
    Bench 5×5, OHP 3×8, Pullup 3×AMRAP, DB curl 3×10, Cable tricep 3×12
  PM (45 min) — Outdoor Run
    5k easy pace
  + Photo (8 AM)
  + Water: 1 quart logged
  + Reading: 10 pages

Tuesday
  AM (45 min) — Lower Lift A
    Squat 5×5, RDL 3×8, Walking lunge 3×10, Leg curl 3×12, Calf raise 4×15
  PM (45 min) — Intervals
    6×400m run, 90s rest
  + Photo, water, reading

Wednesday
  AM (45 min) — Easy cardio (outdoors)
    45 min bike or jog
  PM (45 min) — Mobility flow (outdoors counts)
  + Photo, water, reading

Thursday — same as Monday
Friday — same as Tuesday
Saturday
  AM (60 min) — Long cardio (outdoors)
    Long run or hike
  PM — optional
  + Photo, water, reading

Sunday — Rest (recovery walk OK)
  + Photo, water, reading
```

Each day has a daily checklist surface (the discipline-specific block). Items pulled depending on which contract elements are active.

## Milestones

These are about **streak**, not strength:

1. **Day 7** — first week complete
2. **Day 30** — first month
3. **Day 50** — past the dropout cliff
4. **Day 75** — completion of classic cycle
5. **30 days no miss after first reset** — proves resilience post-failure
6. **150 days total** — repeat completer

Strength PRs and weight loss are **secondary** for this template. They happen incidentally; the user picked this to *do it*, not to PR.

## Adaptation rules

Discipline template doesn't *adapt* in the way other templates do. The contract is the contract. Two specific adaptations:

| Trigger | Adaptation |
|---|---|
| 5+ consecutive completions, lifts feeling easy | Coach offers to up the load (still user-confirmed) |
| Sleep <5 hours, RHR elevated | Coach **does not** suggest skipping — that breaks the contract. Instead suggests the AM workout be lighter cardio rather than heavy lift. Still 2 workouts. |
| User reports "couldn't sleep, exhausted" | Same as above. Adapt the *intensity*, never the *count*. |
| User reports pain | Standard safety handoff overrides contract. *"that's a doctor conversation. that breaks the rules. that's fine."* |

The last one is critical. The discipline template's rules don't override safety. Safety overrides everything.

## HealthKit usage (basic per user's scope)

- **Sleep:** tracked, surfaced — *"4 hours. PM session is a walk, not intervals."* Adapts intensity, not count.
- **Weight:** read and shown but not the metric of focus
- **Steps:** auto-counted; long Sat cardio often shows up here

## Photo block — REQUIRED

This is the only template where the photo block is non-optional.

- Daily, same time (user picks during onboarding — usually morning)
- Same location, same lighting (coach reminds in the prompt)
- Camera opens in-app, photo stored locally + synced to backend (user can opt to keep local-only)
- The Becoming tab gets a **photo grid by week** for this template
- After the cycle completes (e.g. day 75), a "before/after" surface is generated — side by side, day 1 vs day 75

If the user skips a photo, that breaks the streak just like a missed workout. The contract.

## Voice register tuning

Marcus base register with the **second-largest deviation**, but in the *opposite* direction from longevity. Marcus is **sharper** here:

- Shorter sentences than base
- More imperative
- Zero softening
- More references to the contract: *"that's a no. day 1 again. up to you."* — never *"it's okay, life happens"*

But still Marcus — not a Drill (Frisella) impersonation. The line is: he's tough because the user *asked for tough*, not because he's performing it.

Slip-day intervention for discipline (very rare — should not happen often, but when it does):

> Missed. The contract resets. Day 1 tomorrow if you want it. Or we go to soft. Your call.

Notice:
- "The contract resets" — names the rule the user agreed to
- "Day 1 tomorrow if you want it" — doesn't push, offers
- "Or we go to soft" — gives a graceful step-down
- "Your call" — preserves agency

This is the moment the discipline template earns its keep. Most 75-Hard apps just say "you broke it." This says "you broke it; here's how we keep going."

## What this template is NOT for

- People who want flexibility — fundamentally wrong fit
- People with active injuries — the volume will exacerbate
- People with histories of disordered relationship with exercise — the daily/contract framing can be triggering. Quiet referral if detected during intake (referral to a longevity or conditioning template + a soft "this template can become compulsive; if you've struggled with that, the others work too" message)
- True beginners who've never trained — too much, too fast. Recommend strength or conditioning first; come back in 90 days if still interested.

The intake should soft-gate: ask "have you done a strict daily program before?" If no → *"this is intense. consider starting with strength or conditioning for 90 days, then come back."*

## Engineering notes

- File: `backend/coach/personas/discipline.py`
- New intake fields:
  - `goal="discipline"`
  - `cycle: str` (75_classic / 75_soft / 30_starter / open_ended)
  - `contract_items: list[str]` (workouts / photo / water / reading)
  - `photo_time: str` (HH:MM in user's local time)
  - `outdoor_required: bool`
- New module: `backend/coach/discipline_cycle.py` — manages cycle state, days complete, miss = reset logic
- Photo storage: requires actual blob storage. Local-first (camera roll), with optional sync to backend. Storage estimates: ~1MB per photo × 75 days = ~75MB per user per cycle. Manageable.
- New endpoint: `POST /discipline/photo` — accepts image upload
- The Composable Blocks architecture handles the daily-checklist surface as a `DisciplineChecklist` block that only appears for this template

## Open questions for this template

- **Can a user be on discipline AND another template simultaneously?** E.g. "discipline cycle on top of my hypertrophy program." Probably no for v2 — pick one. Could add layered programs in v3.
- **Does the reset on miss apply to the photo or just workouts?** I'd say all contract items count equally — miss any and the streak breaks. But this is the kind of design call worth user-validating.
- **What if a user gets sick for a week?** Hard truth: the contract resets. The 75 Hard tradition holds this position. Should we offer a "medical pause" that preserves the streak? Possibly — but mark it clearly as a "you're using a pause" so the user can't game it. Probably allow 1 pause per cycle, marked.
- **What about travel?** Same answer — the cycle assumes you train wherever you are. Outdoor options scale (a hotel hallway walk counts as outdoor). Travel is a chance for the contract to prove itself.
- **Public commitment / share?** The 75 Hard community is famously vocal on social. The discipline template could ship with a "share my day X" affordance — but doing this thoughtfully (without becoming a humblebrag engine) is real work. Probably v2.1.
- **What happens after cycle completion?** If a user finishes 75 classic, do we offer them another cycle, route them out, suggest a longer one? Probably offer a "second cycle" + a "maintenance" template (likely Strength or Hypertrophy with the photo block kept). This is the "what's next after the streak ends" problem.

## Risk note

Discipline is the template most likely to **attract users with disordered relationships to exercise**, and most likely to *amplify* those patterns if they exist. We should:

1. Include a soft screening question during onboarding: *"have you ever felt unable to stop exercising even when sick or hurt?"* — if yes, route to a gentler template and surface support resources.
2. Have the safety handoff (spec §4.4) be especially aggressive for this template — any pain, fatigue beyond normal, or mental-health language triggers immediate referral.
3. Make the "switch to soft" option always one tap away during the cycle, not buried.

This is the template most likely to drive viral engagement *and* most likely to harm users. We should be honest about both before shipping it.
