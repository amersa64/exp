# Template 01 — Strength

The "get stronger" goal. The current v1 persona, cleanly refactored, with an intermediate-graduation path added.

## Who picks this

The user who said *"I want to move more weight."* Concretely:

- Cares about specific lift numbers (squat / bench / deadlift / OHP)
- Willing to grind the same handful of compound lifts for months
- Trusts that aesthetic outcomes follow from strength outcomes
- Doesn't want isolation work or pump-chasing
- Comfortable with the gym (or wants to be)

Anti-personas (people who should NOT pick this):
- Wants bicep curls and chest fly → Hypertrophy (02)
- Wants to lose weight as the primary metric → Conditioning (03)
- Wants joint-friendly, no-PR-chasing training → Longevity (04)

## Split structure

**Full body A/B alternating, 3 days/week** (Starting Strength / GZCLP tradition).

| Day | Workout | Exercises |
|---|---|---|
| Mon | Workout A | Squat 3×5, Bench 3×5, Row 3×5 |
| Wed | Workout B | Squat 3×5, OHP 3×5, Deadlift 1×5 |
| Fri | Workout A | (repeats with progressed loads) |

Each session hits all major movement patterns: knee-dominant squat, horizontal push, horizontal pull (A) or vertical push, hip hinge (B). Squat appears every workout because frequency is the novice's #1 driver.

### Why A/B alternating and not push/pull/legs

For novice strength, frequency on the main lifts (esp. squat) outweighs muscle-group specialization. A novice can recover from squatting 3×/week; an intermediate cannot. PPL spreads volume out but loses the squat frequency that drives the fastest gains. This split is deliberately *not* a hypertrophy split.

## Rep ranges

- All working sets: **3-5 reps**
- Higher accessories (when added at intermediate stage): **5-8 reps**
- Never above 8 reps as a primary work set

## Progression

**Linear progression** (Starting Strength rule):
- Completed session = next time, **+5 lb upper / +10 lb lower**
- Missed reps = repeat the load next session, no progression
- Two consecutive misses on the same lift = **10% deload** on that lift only

After ~12 weeks of linear progression most novices stall. **Graduation path:** when any major lift fails to progress for 3 consecutive sessions despite a deload, the brain offers:

> *"Linear's done its job. Your squat's at 235. We move to a wave: heavy / medium / light through the week. Want in?"*

User taps yes → program switches to a basic intermediate template (4-day upper/lower with wave loading). This is **internal** to the strength template — same persona, more sophisticated programming layer.

Optional v2.1: graduation prompts go to a dedicated `intermediate_strength.py` sub-persona.

## Days/week supported

| Days | Structure |
|---|---|
| 2 | A / B (one of each per week) — slow but viable; for time-constrained users |
| 3 | A / B / A then B / A / B — alternating across weeks (default) |
| 4 | A / B / A / B — most aggressive novice setup |

Below 2 or above 4 → user should pick a different template.

## Time per session

- Default: **45 min**
- Compressed (30 min): drop accessory reps, tighter rest (90s vs 180s), no warm-up theater
- Extended (60 min): add warm-up sets named, add one accessory (chins, dips)

Time is selected during intake (new Q4 in v2). The persona generates the right-sized session.

## Equipment branches

The template requires a barbell + rack for the canonical experience. Falls back:

| Equipment | What changes |
|---|---|
| Full gym / barbell+rack | Canonical — barbell squat, bench, row, OHP, deadlift |
| Dumbbells only | Goblet squat, DB bench, DB row, DB OHP, DB Romanian deadlift. Loads scale to single-dumbbell capacity. |
| Bodyweight only | **Discourage this template** — pivot user to Conditioning (03). If user insists: bodyweight squat → pistol squat progression, pushup → handstand progression, inverted row → pull-up progression. Progression is rep-based, not load-based. |

## Special considerations

- **Warm-up sets:** intermediates and above need warm-up sets named explicitly. *"Empty bar × 5, 95 × 5, 135 × 3, 185 × 1, then work sets at 220."* For novices, warm-up is a brief instruction; for intermediates, it's part of the prescription.
- **Injuries:** the intake `injuries` field branches the exercise selection. Lower-back tweak → no conventional deadlift this week, RDL substitute. Knee pain → box squat substitute. The branching logic is in the persona, not in the intake form.
- **Baseline lifts:** intake asks for 5RM squat (already does), and ideally also 5RM bench (currently doesn't). v2 should ask both. Bench baseline drives starting bench load.

## Sample week — novice, full gym, 3 days

```
Monday — Workout A (45 min)
  warmup
  Squat 3×5 @ 155 lb · 180s rest
  Bench 3×5 @ 95 lb · 150s rest
  Row 3×5 @ 65 lb · 120s rest

Wednesday — Workout B (40 min)
  warmup
  Squat 3×5 @ 160 lb · 180s rest
  OHP 3×5 @ 55 lb · 150s rest
  Deadlift 1×5 @ 185 lb · 180s rest

Friday — Workout A (45 min)
  warmup
  Squat 3×5 @ 165 lb · 180s rest
  Bench 3×5 @ 100 lb · 150s rest
  Row 3×5 @ 70 lb · 120s rest
```

Squat goes up every session. Bench/row/OHP every other session (since they only appear every other day). Deadlift weekly.

## Milestones

The current `fitness.py` defines three. We keep them:

1. **Squat bodyweight × 5** — early concrete win, usually 4-6 weeks in.
2. **3 sessions/week for 4 weeks** — consistency milestone, the habit-formed flag.
3. **Squat 1.5× bodyweight × 5** — the novice → intermediate threshold.

Suggested addition for v2:

4. **First 5-lb bench progression after a stall** — proves the user pushed through the first plateau.
5. **First successful deload** — proves the user trusted the program at a hard moment.

Milestones 4 and 5 are *resilience* markers — they capture not progress but *how the user handled friction*. Worth as much or more than the strength PRs.

## Adaptation rules (what the brain does with reports)

Same logic as today's v1, cleaned up:

| Report | Brain action |
|---|---|
| Done | +5 upper / +10 lower next session for the worked lifts |
| Partial | Hold load, no progression. Note friction. |
| Skipped | Hold load. Repeat the same session next attempt. No punishment. |
| Done w/ "too easy" | +10 upper / +15 lower (jump rate doubles) |
| 2 consecutive partial on the same lift | 10% deload on that lift |
| 3 consecutive partial after a deload | Graduation prompt to intermediate template |

## HealthKit usage (basic per user's scope)

- **Sleep:** if last night was <6 hours, the brain skips today's progression and holds the load. *"4 hours last night. Same load today, don't push."*
- **Weight:** not central to this template (strength gains can come at any body weight). Show trend on Becoming tab but don't drive prescription.

## Voice register tuning

Marcus base register. No deviations. Strength users self-select for blunt — they want the numbers, not the encouragement.

Slip-day intervention for a strength user:

> Two in a row. Squat went 0. Today's not a bench day or a deload day. Get under the bar at 95 — one set. That's the rule.

Note: for *strength* template users, Marcus can use the phrase "the rule" because it lands as gym vernacular ("the rule of the gym"). For other templates, "the rule" is on the denylist (fortune-cookie). Template-specific exceptions to the voice spec are documented in `../../voice/voice-spec.md` per template.

## What this template is NOT for

- People who want to "look better" — strength gains correlate with aesthetics but slowly. If they want fast aesthetic feedback, route them to Hypertrophy (02).
- People with active back/knee injuries — squat/deadlift loading is unsafe. Route to Conditioning (03) or Longevity (04) until healed.
- People who hate squatting — they will quit. Better to admit this upfront and route them to Hypertrophy (02) which has more variety.

## Engineering notes

- File: `backend/coach/personas/strength.py` (renamed from `fitness.py`)
- Interface: `Persona` (no changes)
- New fields needed in `UserProfile.answers`:
  - `goal: str` (always "get_stronger" for this template)
  - `time_per_session_min: int` (new in v2 intake)
- The graduation logic from novice → intermediate is a new function `_check_graduation_to_intermediate(program, recent_reports)` returning either `None` or a new `ProgramState` representing the upgrade.
- Existing tests in `backend/tests/` (21 of them) all bind to this persona. They become "strength template" tests. Rename test file to `test_strength_persona.py`.

## Open questions for this template

- **Should we offer to add a single conditioning day** (e.g. one 20-min sprint session) without leaving this template? Some strength users want minimal cardio for heart health. Probably yes — but as a Settings-controlled "+1 conditioning day" toggle, not a default.
- **Pull-ups / chin-ups.** The current template has no pulling beyond barbell row. Should it add pull-ups as the "vertical pull" slot? Probably yes for intermediates — but not for true novices who can't do one yet. Conditional add on graduation.
- **Programming for women who don't want to bulk up.** This template doesn't bulk anyone. The cultural fear of "getting too big" from lifting heavy is mostly unfounded. But the *worry* is real and the brand should address it in onboarding copy for the strength template. Add a short reassurance line in the goal-selection screen if female-presenting user picks strength: *"this won't make you bulky. It'll make you strong."*
