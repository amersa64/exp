# Feedback synthesis — program design + onboarding gaps

Trigger: real user installed the app, walked the intake, looked at the prescribed program, found 5 distinct issues. This document digs into each, walks 5 made-up personas through the same path, and proposes specific changes — not all of which fit cleanly into the v2 we'd already designed.

> Honest take up front: the v2 design we built solved the *voice and surface* problem. It did not solve the *program design* problem. The program engine is currently a single hardcoded novice-strength template, the onboarding doesn't ask what the user wants to achieve, and the exercise selection has no swap path. Those are deeper than UX; they're a product gap. This doc owns that.

---

## 1. The "Lower A / Lower B" bug — what's actually happening

The user reported: *"the program is not obvious it is doing legs and squat and the next day we do legs and shoulders??"*

Inspecting `backend/coach/personas/fitness.py`:

```python
def _session_a(...) -> Session:
    return Session(
        name="Lower A",
        exercises=[
            _prescribe("squat", ...),    # lower body
            _prescribe("press", ...),    # upper body PUSH
            _prescribe("row",   ...),    # upper body PULL
        ], ...)

def _session_b(...) -> Session:
    return Session(
        name="Lower B",
        exercises=[
            _prescribe("squat",    ...),  # lower body
            _prescribe("ohp",      ...),  # upper body PUSH
            _prescribe("deadlift", ...),  # hip hinge (mostly posterior chain)
        ], ...)
```

**Both sessions are full-body.** "Lower A / Lower B" is a flat-out misnaming bug, probably left over from an earlier draft that planned an upper/lower split. The programming itself is *correct* Starting Strength / Greyskull novice linear progression — squat every workout, alternate horizontal push (bench A) with vertical push (OHP B), one heavy pull (row A) with one heavy hinge (deadlift B). A real strength coach would recognize this immediately and nod.

But a real **user** who has never seen Starting Strength will see "Lower A" with bench press in it, conclude the app is broken, and lose trust. The bug isn't the program — **the bug is the labels and the lack of transparency about why the structure is the way it is.**

**One-line fix** (proposed below as a quick win):

```python
name="Workout A"  # full body: squat + bench + row
name="Workout B"  # full body: squat + overhead press + deadlift
```

Plus a UI line under the session header that names what muscle groups it hits:

> *"Full body. Quads, chest, mid-back."*  
> *"Full body. Quads, shoulders, posterior chain."*

That alone makes the program legible. The actual exercise selection doesn't change. Maybe ~10 minutes of work end-to-end.

---

## 2. Persona walkthroughs — what 5 made-up users find

The user asked me to do user research with personas. I picked 5 that span the realistic market for this app. Each walks through the current v1 intake and lands on the first prescribed session. I narrate what each notices.

### Persona 1 — Sarah, 32, postpartum return-to-fitness

- 16 months postpartum, hasn't trained since pregnancy
- Was fit before — intermediate level, ran a half-marathon and lifted casually
- Has diastasis recti (mild ab separation), weak pelvic floor
- Goal: lose 15 lb, regain core, feel like herself again
- Equipment: dumbbells + a resistance band at home
- Time: 3 days/week, naptimes, ~30 min sessions
- Has tried two fitness apps post-baby; both quit

**Sarah walks the intake:**

| Q | Sarah's answer | Sarah's reaction |
|---|---|---|
| Welcome | reads tagline | "OK, a coach. Not another tracker. Curious." |
| Experience | intermediate | (selects without hesitation) |
| Days/week | 3 | (selects without hesitation) |
| Injuries | "diastasis recti, weak core post-baby" | "Will it know what that means? Will it be safe?" |
| Equipment | dumbbells | (selects) |
| Baseline squat | "unsure" toggle | "Haven't squatted with weight in 2 years." |
| Anchor habit | "after the baby's nap" | (writes) |
| Location | "the spare room" | (writes) |
| Identity | "someone strong who can carry her kid up the stairs without getting winded" | (writes) |

**Sarah hits the program. She sees:**

- Lower A: dumbbell squat 3×5, pushups 3×5, dumbbell row 3×5

**Sarah's reactions:**

- "Wait, what about my core? I just told it I have diastasis. There's no core work, no pelvic floor, no mention of being careful with deadlifts. Did it read what I wrote?"
- "Pushups, 3 sets of 5 — I can't do one full pushup. And there's no modification mentioned."
- "Where's stretching? Where's any conditioning? I want to lose weight too."
- "It said 'expected 45 min' but I have 30 max during naptime."
- "This feels like a guy's program. I'm not sure this is for me."

**Sarah's verdict:** "Beautifully designed but it doesn't actually understand what I need." Uninstalls within a week.

**What's missing:** goal-aware programming, injury-aware adaptation (using free-text injury input), time-per-session constraint, accessory work for core/mobility, exercise scaling for sub-bodyweight-strength users.

---

### Persona 2 — "Big Marcus", 45, executive, limited time

(Different Marcus from our coach archetype. Sorry for the name collision.)

- VP at a tech company, two kids, runs his own commute
- Lifted on and off for 20 years, intermediate
- Used to bench 225, currently ~180, soft middle
- Goal: maintain fitness, look decent for an upcoming vacation, stress relief
- Equipment: corporate gym in office building, fully equipped
- Time: 2-3 days/week, **30 min max** including warmup
- Tried Fitbod, dropped off because "the workouts were too long"

**Big Marcus walks the intake:**

- Experience: intermediate
- Days/week: 3 (would have picked 2 if available, but app caps at 2-4 so picks 3)
- Injuries: "old lower back tweak from last year, mostly fine"
- Equipment: full gym
- Baseline squat: "315 for 5" (writes 315)
- Anchor: "right after work, before going home"
- Location: "the office gym"
- Identity: "the strong dad my kids see"

**Big Marcus hits the program. He sees:**

- Lower A: squat 3×5 @ 220 lb (started at 70% of 315), bench 3×5 @ 65 lb, row 3×5 @ 65 lb

**Big Marcus's reactions:**

- "Why is bench at 65 lb? I bench 180. Why is row at 65? These accessories are at beginner load while squat is at my intermediate load."
- "No warm-up sets named. I'm supposed to do 3 working sets of 220 squat cold? That's how you tear something at 45."
- "Expected 45 min. I have 30. This needs to compress."
- "Where's my upper body day? I want to look good in a t-shirt by August, not just squat a lot."
- "The progression rule says +10 lb squat next session. I'm an intermediate — linear progression has been over for me for 15 years. I'd plateau by week 4."

**Big Marcus's verdict:** "This is a beginner's program. I said intermediate, the app collected it, then ignored it." Tries the next session, gets bored, never returns.

**What's missing:** experience-aware programming (intermediates need different periodization), per-lift baseline (not just squat), time-per-session respect, warm-up structure, hypertrophy/aesthetics-aware programming, goal-aware programming.

---

### Persona 3 — Tyler, 23, "wants to get jacked"

- Recent college grad, athletic in HS football
- Never lifted seriously, watches a lot of fitness YouTube
- Goal: build muscle, especially arms and chest. "I want to fill out a t-shirt."
- Equipment: 24 Hour Fitness membership
- Time: 5-6 days/week, has all the time in the world

**Tyler walks the intake:**

- Experience: novice (honest)
- Days/week: **wants 5, app caps at 4.** Picks 4 reluctantly.
- Injuries: none
- Equipment: full gym
- Baseline squat: unsure
- Anchor: "after my morning protein shake"
- Location: "24 Hour Fitness on Main"
- Identity: "the guy with the big arms"

**Tyler hits the program. He sees:**

- Lower A: squat, bench, row
- Lower B: squat, OHP, deadlift

**Tyler's reactions:**

- "Where are the bicep curls? Where's any arm work?"
- "5 sets of 3-5 reps? That's for strength. I want to grow. Should be 3-4 sets of 8-12."
- "Squat every workout — I don't even care about legs."
- "No isolation work at all. Where's chest fly? Lateral raises? Skull crushers?"
- "Only 4 days a week — I want to be in the gym every day."
- "The app is telling me to do a powerlifting routine. I'm trying to look good, not compete."

**Tyler's verdict:** "This is for old powerlifters." Downloads Fitness AI instead.

**What's missing:** hypertrophy programming (8-12 rep range, isolation work, body part splits), 5-6 day options, goal-of-aesthetics path, ability to specify focus muscle groups.

---

### Persona 4 — Diane, 58, sedentary, longevity goal

- Recently retired, walked daily but never lifted
- Goal: "be stronger so I don't fall when I'm 70." Has read about sarcopenia.
- Slightly concerned about her balance
- Equipment: light dumbbells (5-10 lb) at home, nothing else
- Time: 3 days/week, mornings, 30-45 min

**Diane walks the intake:**

- Experience: "none — never trained"
- Days/week: 3
- Injuries: "knees creak a bit when going downstairs"
- Equipment: dumbbells (closest match)
- Baseline squat: "unsure" — has never squatted with weight
- Anchor: "after my morning tea"
- Location: "my living room"
- Identity: "a woman who can still lift her own suitcase at 80"

**Diane hits the program. She sees:**

- Lower A: dumbbell squat 3×5 @ no load specified, pushups 3×5, dumbbell row 3×5

**Diane's reactions:**

- "Pushups? I can't do a pushup. I haven't been able to do a pushup in 30 years."
- "It says 'first instruction: Begin in a high plank position with hands directly under your shoulders.' I don't know what 'high plank' means."
- "It assumes I know what a 'row' is. I had to look it up."
- "Where's balance work? Where's the longevity stuff I've read about?"
- "The whole vibe is for a strong young person."

**Diane's verdict:** "This isn't really for me." Doesn't come back.

**What's missing:** beginner-true-beginner scaling (assisted pushups, box squats), longevity/general-fitness track with balance work, vocabulary that doesn't assume gym knowledge, possibly age-aware programming choices.

---

### Persona 5 — Hassan, 35, 75 Hard veteran

- Did 75 Hard twice, both completed
- Intermediate lifter, ~5 years consistent training
- Goal: maintain discipline, push intensity, photo accountability
- Equipment: home garage gym (rack, bar, plates, dumbbells)
- Time: 6 days/week, two-a-days sometimes
- Wants strictness

**Hassan walks the intake:**

- Experience: intermediate
- Days/week: **wants 6. App caps at 4.** Closes app. Done.

**Hassan's verdict:** "App doesn't even let me train how I train." Never gets to see the program.

**What's missing:** 5-6 day program options, hardcore-user path, two-a-day support, photo accountability (75 Hard is famously about the daily photo).

---

## 3. Synthesis: what 5 personas tell us

| User complaint | Personas affected | Root cause |
|---|---|---|
| Naming ("Lower A/B" makes no sense) | All 5 | One-line bug — labels don't match contents |
| Program doesn't fit their goal | Sarah, Big Marcus, Tyler, Diane, Hassan | **Only one program template exists** — novice linear strength. No goal-based variants. |
| Onboarding ignores key inputs (injuries, time, focus areas) | Sarah, Big Marcus, Diane | Intake collects fields but doesn't shape the program from them |
| Today page is confusing | All 5 (implicitly) | Already addressed in v2 redesign |
| No way to swap exercises | Sarah (pushups), Diane (pushups), Tyler (wants curls) | Backend has a catalog with 870 exercises and movement-pattern ladders — UI never exposes this |
| No HealthKit / weight / photo tracking | Sarah (wants weight), Hassan (75 Hard photos), Big Marcus (wants progress) | HealthKitService.swift exists but is never user-visible |
| Schedule cap (2-4 days) | Tyler, Hassan | Hardcoded range that excludes the high-frequency user segment |
| No time-per-session constraint | Big Marcus, Diane | Not asked during intake; sessions can't compress |

**The headline:** the app's *single* program template is what blocks most personas. Five personas, five different program needs, one program. Even Marcus the novice-strength user — the *target* persona for v1's hardcoded template — would benefit from the program being labeled correctly and its structure being visible.

---

## 4. Proposed fixes — by priority

### TIER 1 — ship this week (quick wins, big leverage)

#### 1a. Fix the "Lower A/B" naming bug

```python
# backend/coach/personas/fitness.py
name="Workout A"  # was "Lower A"
name="Workout B"  # was "Lower B"
```

Plus add a `muscle_groups_summary` field to `Session`:

```python
# Workout A: "Full body — quads, chest, mid-back"
# Workout B: "Full body — quads, shoulders, posterior chain"
```

Render this as a subtitle under the session name on the Now/Train tab. **One-line code change + one new field + one UI render.** Probably 30 minutes end-to-end.

#### 1b. Goal-first onboarding (Q1 becomes "What are you trying to do?")

Replace the current Q1 (experience) with a new Q0 (goal). Five options:

| Option | Description | Maps to program template |
|---|---|---|
| Build muscle | "Look bigger. Fill out a t-shirt." | Hypertrophy PPL (6+ days) or Upper/Lower (4 days) |
| Get stronger | "Move more weight." | Linear progression (current) |
| Lose weight, get fit | "Drop fat, feel better." | Full-body conditioning + circuits |
| Stay fit, age well | "Maintain. Don't get injured." | Mobility + 2-3 day full body |
| 75-Hard-style discipline | "Strict, daily, photos." | 6-day discipline track with photos required |

The goal then **gates** the next questions. A hypertrophy user gets asked about focus muscle groups; a longevity user gets asked about mobility goals; a 75-Hard user gets asked about photo cadence. **The intake becomes adaptive, not fixed.**

This is the single biggest change. It turns the app from "one program for everyone" into "different programs from a shared engine."

#### 1c. Today tab is already going away in v2

Validated by the user's reaction. Stays on plan: Today folds into the new Coach tab.

---

### TIER 2 — ship in v2 (the bigger redesign)

#### 2a. Add 4 more program templates (one per goal)

Currently `backend/coach/personas/` has just `fitness.py` (novice linear). Add:

| File | For | Source structure |
|---|---|---|
| `fitness_strength.py` | Get stronger (current, rebranded) | Starting Strength / GZCLP linear progression |
| `fitness_hypertrophy.py` | Build muscle | Upper/Lower (4d) or PPL (6d), 8-12 rep range, accessory work |
| `fitness_conditioning.py` | Lose weight | Full-body circuits 3d + 2 cardio/conditioning days |
| `fitness_longevity.py` | Stay fit, age well | Full body 2-3d, mobility, balance, light loads |
| `fitness_discipline.py` | 75-Hard-style | 2 workouts/day, photo required, strict no-skip |

Each conforms to the existing `Persona` interface (the architecture already supports this — see `Persona is a data-class of callables` in the README). Adding a new persona is authoring a new file, not editing the engine. This is exactly what the spec §G2 ("Authorable personas") was set up for.

#### 2b. Time-per-session question

Add Q2 (after goal): "How long can you train per session?"

- 20 min — express
- 30 min — short
- 45 min — standard
- 60+ min — full

The persona uses this to compress the session: fewer accessory exercises, supersetted main lifts, no rest-time fluff. A 45-min program isn't a 30-min program with the same exercises.

#### 2c. Specific focus areas question (conditional)

After goal: ask which muscle groups they care about most. **Only for users whose goal benefits from focus** — hypertrophy and aesthetics users. A "get stronger" user is told there are no shortcuts, programming compounds; no focus question for them.

#### 2d. Exercise swap UI

Every exercise row gets a "swap" affordance (icon, long-press, or three-dot menu). Tapping shows **3 alternates** using the existing `_SLOT_LADDERS` data + movement-pattern matching from the exercise catalog. Rules for what counts as a true alternate:

| Rule | Implementation |
|---|---|
| Same movement pattern | Knee-dominant push → knee-dominant push; never knee-dominant for hinge |
| Same primary muscle | Upper chest → upper chest; not upper chest → lower chest |
| User has equipment | Filter by user's equipment profile |
| Difficulty within ±1 level | Beginner → beginner or intermediate, not beginner → advanced |

The exercise dataset (`backend/data/exercises.json`, ~870 exercises) already has `primary_muscles`, `secondary_muscles`, `mechanic`, `level`, and `equipment` fields. The swap logic is mostly *querying* what exists, not building anything new.

#### 2e. Schedule range

Change Q from 2-4 to **1-6 days**. Some users want 6; some users want 1 (rehab/postpartum/aged). The current 2-4 range excludes both ends of the market.

#### 2f. HealthKit integration

Three concrete surfaces:

1. **Weight tracking** — read HealthKit body mass. Show trend on the Becoming tab. The coach references it: *"down 4 lb in 6 weeks. Don't push it."*
2. **Sleep summary** — read HealthKit sleep. Use it in Stage 1 planner context. The coach references it: *"3 hours last night. Skip squat today, do mobility."*
3. **Photo upload** (NOT HealthKit, but on-brand) — manual camera upload for 75-Hard-style users. Becomes a block in the composable architecture (see `v2/composable-blocks.md`).

Weight and sleep are read-only HealthKit. Cheap. iOS Permission prompts during onboarding for users whose program needs them (the discipline + lose-weight personas).

---

### TIER 3 — backlog (not yet)

- Equipment-aware exercise demos (video / animated)
- Form-check via camera (Fitness AI does this)
- Voice-memo replies to the coach
- Community / accountability partner
- Apple Watch app
- Wearable HR / readiness scoring

---

## 5. Updates to the v2 design we already wrote

Our v2 design (`design/v2/`) covered surface and voice but assumed the v1 program engine was fine. It isn't. Three updates needed:

### Update 1: Intake-v2 needs a goal question FIRST

[`design/v2/screens/05-intake-v2.md`](../v2/screens/05-intake-v2.md) currently has the new Q8 (past-failure) but keeps the structure as experience-first. **It should start with goal.** New Q1: "What are you trying to do?" Five options as above. Everything else flows from this.

Revised intake order:

```
Q1. Goal                        ← NEW
Q2. Experience                  ← was Q1
Q3. Days per week (1-6)         ← was Q2, range widened
Q4. Time per session            ← NEW
Q5. Focus muscles (conditional) ← NEW, only for hypertrophy/aesthetics goals
Q6. Injuries                    ← was Q3
Q7. Equipment                   ← was Q4
Q8. Baseline lifts (conditional)← was Q5, only for strength/hypertrophy goals
Q9. Anchor habit                ← was Q6
Q10. Location                   ← was Q7
Q11. What killed your last attempt? ← was Q8 (new in v2)
Q12. Identity statement         ← was Q9
```

That's 12 questions for some users, 8-10 for others depending on goal. The "Five minutes" promise still holds — most of these are clicks, not free text.

### Update 2: Now tab needs exercise-swap, muscle-group summary, warmup-set transparency

[`design/v2/screens/02-now-tab.md`](../v2/screens/02-now-tab.md) needs:

- Subtitle under session name: "Full body — quads, chest, mid-back"
- Each `ExerciseRow` block gets a "swap" icon (three-dot menu)
- Tapping swap shows a sheet: 3 alternate exercises with the same movement pattern + primary muscle, filtered by user's equipment
- Add a "warm-up" section above the working sets, surfaced when the user is an intermediate (Big Marcus's complaint)

### Update 3: Becoming tab needs HealthKit-driven progress

[`design/v2/screens/03-becoming-tab.md`](../v2/screens/03-becoming-tab.md) currently has VotesCard + MountainHero + Stats + Milestones + Habits. Add:

- **Weight trend card** (if HealthKit weight available) — sparkline, current weight, change vs 30 days ago, coach line
- **Sleep readiness strip** (if HealthKit sleep available) — last 7 days, coach line
- **Photo grid** (for users on the discipline track) — calendar grid of daily check-in photos

---

## 6. What this means for the user

The user's feedback validates a uncomfortable truth: **we designed a beautiful surface for a poorly-scoped product.** The v2 work (3 tabs, Coach as front door, slip-day intervention, weekly letter, Marcus voice) is good — but it would have failed in market because the underlying program is too narrow.

The pivot is clear:
1. v2 ships **goal-based** onboarding + **multiple program templates**, not just the surface redesign
2. The composable-blocks architecture we just designed becomes the natural home for goal-segment-specific blocks (photo for discipline, weight for fat loss, mobility for longevity)
3. The Marcus voice still wins regardless of program — different goals, same calm older brother

**Sequencing this matters:**

- TIER 1 fixes ship in v1.1 (this week) — naming bug + goal-first onboarding question that maps to existing template. Test with the user to validate the goal question lands.
- TIER 2 fixes ship in v2 — additional personas, swap, time-per-session, HealthKit. This is more substantial; ~3-4 weeks of work.
- TIER 3 stays in backlog.

## 7. What I'd want from the user before going further

Before I touch code or update v2 designs:

1. **Confirm the 5 goals are right.** Are these the segments we want to serve? Add/remove?
2. **Confirm the persona archetypes feel real.** Did I miss a critical user type? (Athletes prepping for an event? Senior over 70? Rehab from major surgery?)
3. **Pick what ships first.** Quick win (naming + goal Q only) OR wait for full v2 redesign?
4. **HealthKit scope.** Weight + sleep only, or also energy expenditure, HR, VO2max?
5. **Photo tracking — do we commit?** It's a 75-Hard-segment hook but adds upload UI, storage, privacy considerations.

Once those are answered, I'll update the v2 design files in place and we can move to implementation.

---

## Appendix — quotes from the persona walkthroughs, for the voice work

Phrases the personas used that should inform Marcus's voice when speaking to each segment:

- **Sarah (postpartum):** "Will it know what that means?" → voice needs to *demonstrate* injury awareness, not just say "got it."
- **Big Marcus (executive):** "I have 30 minutes." → voice respects time, doesn't moralize about it.
- **Tyler (aesthetics):** "Where are the bicep curls?" → voice can be honest about what builds muscle vs what users *think* builds muscle. Marcus would say: *"curls come after the bench gets to 185. trust the order."* — not preachy, just declarative.
- **Diane (longevity):** "I had to look it up." → voice avoids jargon entirely for this persona; "row" becomes "pull the weight toward your ribs."
- **Hassan (discipline):** "Doesn't even let me train how I train." → voice never adds friction; if user wants 6 days, give 6 days.

These segment-specific voice tunings are well within the older-brother register. Marcus would actually talk differently to Sarah than to Hassan — same person, different conversation. The voice spec just needs to acknowledge this and not flatten it.
