# Template 03 — Conditioning

The "lose weight, get fit" goal. Largest segment by population. The hardest template to get right because the failure mode here is the *exact* dropout pattern our differentiator targets.

## Who picks this

The user who said *"I want to drop fat and feel better."* Concretely:

- Cares about body weight as the primary visible metric
- Mixed background — some have lifted, some haven't
- Often tried diet+app combos that failed
- Wants to feel less winded going up stairs
- Less interested in the "fitness identity" than in "looking and feeling normal again"
- Sarah from the persona walkthroughs is partially this segment (postpartum recovery shares the conditioning frame)
- Big Marcus is partially this too (executive wanting to "look decent for vacation")

This is the segment that historically gets sold *the most* and *the worst* — every fad app targets weight loss, most fail, all leave the user feeling worse about themselves. **The Coach's job here is not to be the fastest weight-loss app. It's to be the one that's still here in month 4.**

Anti-personas:
- Wants explicit muscle gain → Hypertrophy
- Wants explicit PRs → Strength
- Wants only-once-a-week → Longevity

## Split structure

**Hybrid: 3 lift days + 2 conditioning days (5 days total)** — but compressible to 3 total.

| Day | Workout | Focus |
|---|---|---|
| Mon | Full Body Lift A | Squat, push, pull — moderate weight, moderate reps |
| Tue | Conditioning A | 25-30 min steady cardio (run, bike, swim, brisk walk) |
| Wed | Full Body Lift B | Deadlift variant, press, row variations |
| Thu | Conditioning B | Interval work (20 min) OR active recovery (walk + mobility) |
| Fri | Full Body Lift C | Compound circuit — strength endurance |
| Sat-Sun | rest (or one optional active recovery walk) |

The lift days build lean muscle (which raises metabolic rate). The conditioning days create the caloric expenditure that drives weight loss. **Both are mandatory** — you can't out-cardio a bad lifting program, and you can't lose body fat efficiently with weights alone.

### Compressed 3-day version

| Day | Workout |
|---|---|
| Mon | Full Body Lift + 10 min conditioning finisher |
| Wed | Full Body Lift + 10 min conditioning finisher |
| Fri | Full Body Lift + 10 min conditioning finisher |

The conditioning collapses into a *finisher* on each lift day. Less effective for weight loss but realistic for time-constrained users.

## Rep ranges

Strength-endurance bias — moderate reps with shorter rest:

- Compound lifts: **6-10 reps**, 3 sets, 90s rest
- Accessory: **10-15 reps**, 2-3 sets, 60s rest
- Conditioning finishers: AMRAP / EMOM / circuit work, 5-15 min

Higher reps + shorter rest = more total work in less time = more calories burned per session. Different goal from hypertrophy (where rest is longer to maintain load).

## Progression

**Frequency-first, not load-first.** The metric isn't "+5 lb every session"; it's "did you train 4 times this week."

- Lift sessions: small load adds (+2.5 lb upper, +5 lb lower) every other session when reps are at the top
- Conditioning: distance/pace creeps slowly (Week 1: 25-min walk; Week 6: 30-min jog; Week 12: 30-min run)
- The brain tracks adherence > performance for this template

This is critical: a conditioning user who PRs their squat but loses no weight feels they failed. A conditioning user who maintains their lifts and drops 8 lb feels they won. The success metric is body composition, not strength numbers.

## Days/week supported

- 2 → drop to "lift only" or "conditioning only", warn user this is suboptimal
- 3 → compressed (lift + finisher) version
- 4 → 3 lifts + 1 conditioning (good intermediate)
- 5 → canonical (3 + 2)
- 6 → adds active recovery walk; effectively same as 5 with more low-intensity volume

## Time per session

- Default: **30-45 min**
- Conditioning days can be 20 min if intensity is high (intervals)
- Lift days need 30 min minimum for a full body workout

The time-per-session question is *especially* important here because conditioning users often have limited time (they're trying to fit fitness in around a real life, not center their life around it).

## Equipment branches

| Equipment | What changes |
|---|---|
| Full gym | Canonical — barbell + cable + treadmill/bike/rower |
| Barbell+rack at home | Conditioning happens outside (run, walk, bike) |
| Dumbbells only | Substitutes lifts to DB versions; conditioning still outside |
| Bodyweight only | **Best-fit template for bodyweight users.** Circuits, calisthenics, walking/running. Doesn't need equipment. |

Worth noting: this is the *one* template where bodyweight is fully viable. The other templates penalize the user for not having equipment. Conditioning embraces it.

## Special considerations

### Weight loss expectations

The intake should set honest expectations:

> *"Real fat loss is 1-2 lb per week, most weeks. Some weeks zero. Don't expect daily progress on the scale."*

Otherwise the user, conditioned by reality-TV weight loss narratives, will think 1 lb/week is a failure and quit by week 3.

### Diet is out of scope

The Coach does not prescribe nutrition. This is a deliberate boundary (spec §4.4 — know the edge of competence). But conditioning users will ask. The coach response should be specific and useful:

> *"calories. you know this. eat ~500 below maintenance, mostly protein. that's not my job to track. I just lift you and run you."*

Don't dance around it. Don't pretend it doesn't matter. Don't offer to count macros. Refer.

### The compounding-disappointment trap

Most conditioning users have failed before. They will fail again unless we explicitly design for it. The slip-day intervention (Coach Shape C) is most valuable for this template. Recommended escalation:

- Day 1 miss: standard tone
- Day 2 miss: slip-day intervention
- Day 3 miss: program adapts — drop one lift day, replace with a 15-min walk. *"the program isn't working as-is. less is more this week."*
- Day 5+ miss: Return-after-absence (Shape D)

The adaptation on day 3 is unique to this template. Strength template stays the same; conditioning template *reduces volume* to lower the bar to re-entry. This is the "make showing up easier" lever Atomic Habits Ch.13 calls for.

## Sample week — full gym, 5 days

```
Monday — Lift A (40 min)
  Squat 3×8 @ 135 lb · 90s
  Bench 3×8 @ 95 lb · 90s
  Row 3×10 @ 85 lb · 60s
  Plank 3×30s · 30s

Tuesday — Conditioning A (30 min)
  25 min steady run/bike/swim/brisk walk (zone 2)
  cooldown stretch 5 min

Wednesday — Lift B (40 min)
  Romanian Deadlift 3×8 @ 135 lb · 90s
  Overhead Press 3×8 @ 65 lb · 90s
  Pull-up or Lat Pulldown 3×8-10 · 90s
  Walking Lunge 3×10/leg · 60s

Thursday — Conditioning B (20 min)
  Warmup 3 min easy
  6 × 1 min hard / 1 min easy intervals
  cooldown 3 min

Friday — Lift C / Circuit (35 min)
  3 rounds:
    Goblet Squat 12 @ 30 lb DB
    Push-up 10
    DB Row 12/side @ 30 lb
    Plank 30s
    Rest 90s between rounds
  Finisher: 10 min jump rope or step machine

Sat-Sun rest (one optional walk)
```

## Milestones

Carefully chosen to not be weight-only (weight is volatile, user shouldn't anchor identity to it):

1. **4 weeks consistent** — 18+ sessions in 4 weeks (consistency as the foundation)
2. **First measurable weight drop sustained 2 weeks** — first time the scale stays down
3. **First time running 5k continuous** OR **first time biking 10 miles** OR **first time swimming 1km** (user picks at intake)
4. **Bench bodyweight × 5** OR **Squat 1.25× bodyweight × 5** (a strength milestone proves the lifts haven't been hollow)
5. **First photo comparison** — 8 weeks in, side-by-side with intake

Body weight milestones are deliberately NOT here. Why: weight is too volatile to be a milestone. A milestone fires once and stays earned. Weight can come back. Distance and strength PRs can't.

## Adaptation rules

| Report | Brain action |
|---|---|
| Lift Done | Small load add per double progression |
| Conditioning Done | Note pace; suggest +1 min next session if RPE allowed |
| Partial (any) | Hold load/distance, no progression |
| Skipped (1st) | Normal slip handling |
| Skipped (2nd in week) | Reduce next week's lift volume by 20% — make showing up easier |
| Skipped (3rd in 2 weeks) | Drop one lift day, sub a walk. *"less, but real"* |

The volume-reduction-on-slip is the key adaptation that other templates don't have. Conditioning users are *exhausted* — that's often why they're not training. Asking them to push harder is the wrong move; ask less so they can keep going at all.

## HealthKit usage (basic per user's scope)

This template uses HealthKit more than any other:

- **Weight:** read daily if available. Show 7-day rolling average (not daily — too noisy). Coach references it weekly: *"down 3 lb on the average. that's the win."*
- **Sleep:** if last 3 nights avg <6 hours, **swap today's conditioning for an active recovery walk** (don't push fatigued + sleep-deprived users into intervals — recipe for injury).
- **Steps (auto-tracked):** if HealthKit shows >10k steps already today, the conditioning prescription acknowledges it: *"you walked 12k today. that counts. tomorrow's the run."*

This is the template where HealthKit data **actively shapes the prescription**, not just decorates the Becoming tab.

## Photo block

Recommended. The conditioning user often experiences the body-composition change *visually* before the scale catches up — photos catch it.

Cadence: **weekly** (not daily — that's discipline-template). Same time, same light, same outfit. Soft prompt in onboarding: *"want a weekly photo? mirror catches what the scale misses."*

## Voice register tuning

Marcus base register with two specific deviations for this template:

1. **No body-shaming language ever, even mildly.** Phrases like "soft middle" (which I used in Big Marcus's persona profile) NEVER come from Marcus's mouth. The user thinks that about themselves; Marcus does not. He talks about *what we're doing*, not *what's wrong with the body*.
2. **Explicit weight callouts are rare and never dramatic.** The brain knows the weight; Marcus mentions it once a week in the letter, not every session. Daily weight commentary kills users.

Slip-day intervention for conditioning user:

> Two missed. The lift day's gone. Today: a 20-minute walk. Tomorrow we lift, lighter. We adjust.

Notice: it doesn't push for the lost session. It adjusts the program. This is the volume-reduction adaptation surfaced in voice.

## What this template is NOT for

- People who want to track macros — that's a separate tool's job
- People who want six-pack abs in 8 weeks — they will fail and blame us
- Active eating disorder histories — explicit referral, not training (handled by spec §4.4 safety boundary)
- People who already lift consistently and want more performance → wrong template

## Engineering notes

- File: `backend/coach/personas/conditioning.py`
- New intake fields: `goal="lose_weight"`, `current_weight_lb`, `target_weight_lb` (optional — many users don't have a target and that's fine), `conditioning_preference: str` (run / bike / swim / walk / mixed)
- New module: `backend/coach/conditioning.py` — generates conditioning sessions (intervals, steady state, circuits) the way `personas/strength.py` generates lift sessions
- The volume-reduction-on-slip is a new adaptation primitive not in v1; lives in `progression_rules()` for this persona
- HealthKit weight integration: requires a `WeightReading` data type in `backend/coach/models.py` + `GET /healthkit/weight` endpoint. iOS pushes readings on each app open.

## Open questions for this template

- **How aggressive should the program be at week 1?** A 5-day-per-week program at week 1 for an overweight sedentary user is brutal. Probably need a *ramp* — week 1: 2 lift + 1 walk; week 2: 3 lift + 1 walk; week 3: full. Add this to the persona.
- **Should the slip adaptation be transparent?** When we drop a lift day after a 3rd miss, do we tell the user "we're adjusting" or just silently change the next prescription? Probably tell them — but in voice: *"3 missed. we cut Friday this week. one less to lose."*
- **Should we allow a "race goal"** (e.g. "I want to run a 5k in 6 months")? It changes the conditioning programming significantly. Probably not in v2 — too persona-specific. v2.1 maybe.
- **What about supplements / pre-workout / fat burners?** The space is full of grifts. The coach should answer one way: *"no. food, sleep, the work."* Hard line. Worth a canned response.
