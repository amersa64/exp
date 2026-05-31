# 01 — Coach tab (the moat)

The default landing. Where the coach speaks. One tab, five possible shapes — picked server-side based on user state. This is the surface that separates us from every other app on the shelf.

## Role

The Coach tab is **the app's voice**. Other tabs are reference (Now = the prescription, Becoming = the identity). This tab is where the relationship lives. When the user cold-opens the app, they don't land on a workout — they land on the coach having something to say (or, on a quiet day, the coach saying nothing much).

This is also where v2's two differentiating surfaces live: **Shape C** (slip-day intervention) and **Shape D** (return-after-absence). Those two shapes are the entire commercial bet.

## The 5 shapes

The backend's `coachState` endpoint returns a `shape` field. The tab renders one of:

| Shape | When | What it does |
|---|---|---|
| **A — Quiet** | Rest day, nothing prescribed today | Brief check-in, mentions tomorrow |
| **B — Prescription** | Training day | Names the session, the script, the load change |
| **C — Slip** | 2+ consecutive misses | The intervention. Calls out the pattern. Offers a minimum dose. |
| **D — Return** | 5+ days no event | "Haven't seen you in a bit. Still in?" — three buttons |
| **E — Pause-ack** | User chose to pause | Acknowledges the pause; coach is silent until resume |

A single user, on a single day, sees exactly one shape on this tab.

---

## Shape A — Quiet day

```
┌─────────────────────────────┐
│ ⚙           Coach      ●27 │  ← votes badge (no streak)
├─────────────────────────────┤
│                             │
│ FROM YOUR COACH             │  ← small eyebrow
│                             │
│ Off today.                  │  ← coach voice
│ Tomorrow's Full B —         │     (3 short lines)
│ coffee, garage. Get a       │
│ good night.                 │
│                             │
│ ┌─────────────────────────┐ │
│ │ See tomorrow's session  ›│ │  ← secondary CTA (ghost)
│ └─────────────────────────┘ │
│                             │
│ ─────────────────────────── │
│                             │
│ FOLLOW-UPS                  │  ← optional, only if owed
│ (none today)                │
│                             │
├─────────────────────────────┤
│  Coach  ·  Now  ·  Becoming │  ← 3 tabs
└─────────────────────────────┘
```

**Behavior:**
- The coach line is generated through the voice pipeline (see `../../voice/pipeline.md`).
- The "See tomorrow's session" CTA navigates to Now tab.
- Follow-ups section is hidden entirely when none are owed (don't show "all clear" — that adds noise).

---

## Shape B — Prescription day

```
┌─────────────────────────────┐
│ ⚙           Coach      ●27 │
├─────────────────────────────┤
│                             │
│ FROM YOUR COACH             │
│                             │
│ Full A today. After         │  ← named session, the script
│ coffee, garage. Squat       │
│ goes to 150 — warm up       │
│ properly, first set'll      │
│ feel heavy. Bench and       │
│ row hold.                   │
│                             │
│ ┌─────────────────────────┐ │
│ │  Show me the session    │ │  ← primary CTA, ember
│ └─────────────────────────┘ │
│ ┌─────────────────────────┐ │
│ │ ·  I can't today  ·     │ │  ← secondary, ghost
│ └─────────────────────────┘ │
│                             │
└─────────────────────────────┘
```

**Behavior:**
- "Show me the session" → Now tab (programmatic tab switch, not modal).
- "I can't today" → opens a sheet asking *why*. Three options + free text:
  - "Schedule conflict — try later today"
  - "Schedule conflict — try tomorrow"
  - "Body needs a day"
- Each maps to a different brain response: reschedule, skip, deload.

> The "I can't today" affordance is important. Without it, a user with a conflict has no friction-free path other than ignoring the prescription. We want them to *report*, even when they're saying no. Reporting "no" is still a vote for the relationship.

---

## Shape C — Slip-day intervention (THE MOAT)

This is the most carefully-designed surface in v2. It is rendered when the user has missed 2 consecutive sessions (either reported "skipped" twice, or had two scheduled training days pass without any event logged).

```
┌─────────────────────────────┐
│ ⚙           Coach      ●24 │
├─────────────────────────────┤
│                             │
│ FROM YOUR COACH             │
│                             │
│ Two in a row.               │  ← starts blunt, factual
│ Something's getting in      │
│ the way. I want to know     │     audit question
│ what.                       │
│                             │
│ Today: one set of squats    │  ← concrete prescription
│ at 95. That's it.           │     (the minimum dose)
│ Tap in after.               │
│                             │
│ ┌─────────────────────────┐ │
│ │  I did the minimum      │ │  ← primary CTA
│ └─────────────────────────┘ │
│                             │
│ ─────────────────────────── │
│                             │
│ WHAT'S GETTING IN THE WAY   │  ← eyebrow
│                             │
│ ┌─────────────────────────┐ │
│ │ Pick one — or type your │ │
│ │ own.                    │ │
│ │                         │ │
│ │ [· work got busy     ·] │ │  ← pre-baked friction tags
│ │ [· body's off        ·] │ │     (4 options + custom)
│ │ [· lost the routine  ·] │ │
│ │ [· something else    ·] │ │
│ │                         │ │
│ │ {selecting "something   │ │
│ │ else" reveals a text    │ │
│ │ field}                  │ │
│ └─────────────────────────┘ │
│                             │
└─────────────────────────────┘
```

**Behavior:**

- The opening coach line is *base register, slightly sharper*. The voice spec calls for short, factual, no softening. The pre-baked friction tags use the user's own colloquial wording — these are content-authored, not generated, because consistency across users matters.
- The "I did the minimum" CTA logs a verified event with `outcome=done, friction="minimum dose"`. The brain treats it as a vote (Atomic Habits 2-min rule) and the slip counter resets.
- Tapping a friction tag fires `POST /reports/friction` and is fed into the next program adaptation — the LLM rephrases tomorrow's session in light of the named friction.
- The user can do BOTH (do the minimum AND report friction) or EITHER. Both reset the slip counter. The relationship requires a response — not specifically the workout.

**Escalation if Shape C persists:**

If the user lands on Shape C, doesn't engage, and slips a 3rd time the next day, the coach line escalates:

> Three in a row. The program isn't working as-is. Let's change something.

And the "What's getting in the way" section is replaced by a one-question interview that re-runs a slice of intake:

> *"Pick one. Time of day is wrong / equipment is wrong / load is too heavy / too many days per week / something I don't know."*

This is the surface where the coach **adapts the program in real time**, not just the next session. Critically important — most apps treat day-3-of-a-slip the same as day-1. We don't.

**What this surface deliberately avoids:**

- ❌ Streak warnings ("you'll lose your streak!") — we don't have streaks.
- ❌ Guilt copy ("don't give up on yourself") — Marcus would not.
- ❌ Generic re-engagement ("you got this!" pushes) — those make it worse.
- ❌ The word *journey*.

---

## Shape D — Return after absence

Rendered when no `VerifiedEvent` for 5+ days (configurable threshold).

```
┌─────────────────────────────┐
│              Coach     ●24 │
├─────────────────────────────┤
│                             │
│                             │
│ FROM YOUR COACH             │
│                             │
│ Haven't seen you in a       │  ← warmer than C
│ bit. Still in?              │     short, no judgement
│                             │
│ ┌─────────────────────────┐ │
│ │  Back in                │ │  ← primary
│ └─────────────────────────┘ │
│                             │
│ ┌─────────────────────────┐ │
│ │ ·  Give me a week     · │ │  ← ghost (pauses 7d)
│ └─────────────────────────┘ │
│                             │
│ ┌─────────────────────────┐ │
│ │ ·  I'm done           · │ │  ← rose-tinted ghost
│ └─────────────────────────┘ │
│                             │
└─────────────────────────────┘
```

**Behavior:**

- **Back in** → routes to a brief reorientation: the coach picks up the program at an appropriately adjusted phase. The brain dials the next session's load back by 5–15% (depending on time off) for safety. The user sees a Shape B with one extra sentence acknowledging the time off: *"Easing back. Squat goes to 140 — last time you had 150. Get a feel for it."*

- **Give me a week** → puts the program in pause state for 7 days. Push notifications suppressed. Auto-resume next Sunday morning with a fresh Shape B. The user is told: *"Off for a week. Picking it up Sunday morning."*

- **I'm done** → confirmation dialog: *"End the program?"* → if yes, program archived (not deleted), Settings shows "Start a new program" button, intake re-opens. The honesty here matters. We refuse to make the exit feel like failure. Some users *should* end this program — wrong domain, wrong moment in life, wrong fit. That's a win for them and us, not a loss.

**This surface is the moat.** Every competitor lets the user ghost silently and then nags them with generic re-engagement pushes that make it worse. We give them three real choices, in voice, with the third being a graceful out. We will lose some users to "I'm done" who would have been re-trapped by a guilt push. We're betting we'll gain more from users who say "I'm out a week" and actually come back — and from word-of-mouth from the users who get told "you tried, that's a thing, no shame."

---

## Shape E — Pause acknowledgment

Rendered while the user is in a pause state (triggered by Shape D's "give me a week" or by Settings).

```
┌─────────────────────────────┐
│              Coach     ●24 │
├─────────────────────────────┤
│                             │
│                             │
│ FROM YOUR COACH             │
│                             │
│ Paused.                     │  ← single word
│ Back on Sunday.             │     coach is quiet
│                             │
│ ┌─────────────────────────┐ │
│ │ ·  Resume now         · │ │  ← user override
│ └─────────────────────────┘ │
│                             │
│ ┌─────────────────────────┐ │
│ │ ·  Extend pause       · │ │
│ └─────────────────────────┘ │
│                             │
└─────────────────────────────┘
```

**Behavior:**

- Coach voice is intentionally minimal. The point of pause is silence. Anything more reads as the coach not respecting the pause.
- "Resume now" → returns to Shape A or B (whichever today is).
- "Extend pause" → opens a tiny sheet: 1 week / 1 month / done.

> If a user is in a pause and opens the app daily anyway, we don't escalate or change shape. Marcus doesn't lecture. Pause means pause.

---

## Follow-ups section (appears under any shape when relevant)

When the user has unanswered nudges (typically from APNs that didn't get a tap), they appear below the main shape:

```
│ ─────────────────────────── │
│                             │
│ FOLLOW-UPS                  │
│                             │
│ ┌─── tinted amber ────────┐ │
│ │ ↩  Tuesday's Full A —    │ │  ← amber card, tappable
│ │    never heard back.     │ │     opens nudge reply sheet
│ │    What happened.    ›   │ │
│ └─────────────────────────┘ │
```

The card text is generated by the voice pipeline against the unanswered nudge's planner intent. Tapping opens the Nudge Reply sheet (see `screens/07-nudge-reply-v2.md`).

---

## Toolbar

```
┌─────────────────────────────┐
│ ⚙           Coach      ●27 │
└─────────────────────────────┘
   ↑                       ↑
 settings                votes
   gear              (just a number)
```

- **Settings gear** (top-leading) — opens settings sheet.
- **Votes badge** (top-trailing) — just `●27`. No streak suffix. Tappable → opens the Becoming tab scrolled to the Votes section.

No back button. No nav title text beyond "Coach". Spare.

---

## Risks

- **Discoverability of the workout.** A new user lands on Coach (not Now) and might not realize the workout is on a different tab. Mitigation: Shape B's "Show me the session" CTA is large, ember-colored, and prominent. On day 1, we may also want a one-time tooltip arrow pointing at the Now tab on the bar.
- **Shape C / D copy carrying the entire brand.** If the voice transformer drifts here even slightly, the differentiator falls. These two surfaces should be the **first** to ship with hand-authored fallbacks. Don't rely on generation for the moat surfaces in v1.
- **The "I'm done" button looking like a footgun.** Some users will tap it accidentally. Confirmation dialog must be unambiguous: *"End the program? Your history stays. You can start a new one anytime."*
- **Push integration.** A nudge fired by the brain shows up on this tab as the active shape *after the push has been delivered or expired*. If the push hasn't fired yet for the current cycle, the tab shows the previous state. We need to be clear about what "now" means on this tab — see backend ticket on `coachState.as_of_timestamp`.

## What this tab is not

This is **not** a feed. There is no infinite scroll. No "previous nudges" list. No history. The Coach tab shows *one* thing, decided by the brain, that the user should hear right now. History lives on the Becoming tab. Quiet is a valid output.

---

## Open questions for designer review

- Does the lack of a tab badge / red dot for unanswered nudges feel right (push principle), or will users miss them? Test.
- Should Shape D's "Give me a week" be the default option (top button) instead of "Back in"? — for users who only land on D after slipping, the easier path might be the better default.
- Is the votes-only badge too lonely? Should we add a small "weeks training" stat next to it for a sense of horizon? Test.
- Should the "From your coach" eyebrow be visible at all, or does it overexplain? Trying it both ways with users is cheap.
