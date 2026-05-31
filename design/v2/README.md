# The Coach — v2

The redesign. Same brain (the spec is preserved), new surface. This directory is the proposed v2 of the iOS app, built around three decisions that came out of the App Store research and the differentiation work:

1. **We're not a tracker. We're a coach.** Every surface is either the coach speaking or the work the user would otherwise do mentally. Anything that reads "dashboard" gets cut.
2. **We solve drop-off.** Most habit apps die on day 14 when the streak breaks. We assume the user will slip, and we design the slip-recovery surfaces to be the best surfaces in the app.
3. **The voice is Marcus.** A specific 38-year-old strength coach. See `../voice/archetype.md`. Every generated string runs through the older-brother voice transformer. No AI slop ships.

## What's different at a glance

| | v1 | v2 |
|---|---|---|
| Tab count | 5 | 3 |
| Default landing | Train tab (workout card) | Coach tab (the coach speaks) |
| Streak number | toolbar + Summit prominent | gone |
| Primary visible counter | Effort + streak | Votes cast |
| Slip-day surface | none — silent | dedicated Coach-tab shape (the moat) |
| Return-after-absence | nothing | dedicated Coach-tab shape with three buttons |
| Weekly letter | nothing | new Sunday-evening surface |
| Intake question count | 8 | 9 (adds past-failure question) |
| Pause/rest | implicit | first-class command in Settings |
| Voice generation | ad-hoc system prompt | two-stage planner → voice transformer |

## What's preserved from v1

- The brain. All of `backend/coach/` keeps working. Mirror principle intact.
- Intake structure (mostly). One new question, two reorderings, copy refresh.
- The growing-world data model — World, Milestones, LivingSystems, VerifiedEvent.
- Implementation intention as a first-class concept (The Script).
- APNs nudge → reply sheet flow.

## What's deleted

- The "Today" tab. Its content folds into the Coach tab.
- The "Habits" and "Milestones" tabs as standalone destinations. They become scroll sections of the new Becoming tab.
- The streak counter as a visible number.
- The "Tick now" dev button on production builds.
- The "Schedule on calendar" button (hidden until F2 Google Calendar OAuth ships).

## Reading order

1. **`FLOW.md`** — the new navigation graph and the Coach-tab state machine. Start here.
2. **`migration.md`** — what v1 surface becomes what in v2; what's dropped.
3. **`screens/01-coach-tab.md`** — the new primary tab with its 5 shapes. This is where the differentiator lives.
4. **`screens/02-now-tab.md`** — the prescription surface.
5. **`screens/03-becoming-tab.md`** — identity, milestones, habits, folded into one tab.
6. **`screens/04-weekly-letter.md`** — the share artifact.
7. The rest in any order: intake, log session, nudge reply, settings, onboarding.

## How this directory relates to the others

```
design/
  screens/        ← v1. What the iOS app looks like today.
  v2/             ← this directory. What it should look like next.
  voice/          ← the coach's voice spec, used by v2 surfaces.
  FLOW.md         ← v1 flow.
  README.md       ← top-level orientation.
```

When this v2 ships, `screens/` becomes historical documentation and v2 becomes the design source of truth. We keep both for one cycle to make the diff legible.

## Status

All files in this directory are **proposals**, not commitments. The screens have not been user-tested. Before any of this becomes engineering tickets:

1. The voice work needs a 5-user resonance check (does Marcus actually land?).
2. The architectural shift to 3 tabs needs a fresh-user discoverability check (can a new user find the workout?).
3. The slip-day and return-after-absence surfaces need to be designed to *high fidelity* and tested against the question: *"would a real user, on day 14 of dropping off, respond to this?"*

If those three checks pass, ship v2. If any fail, revise.
