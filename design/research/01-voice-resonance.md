# 01 — Voice resonance test

A small qualitative study to validate the Marcus voice with real users *before* engineering builds the v2 surfaces around it. If the voice doesn't land, no amount of architectural polish will save us — the whole differentiator rests on the user feeling like they're being addressed by a person, not an AI app.

## Goal

Answer one question:

> **Would a representative target user — a person who's tried and bounced off habit/fitness apps before — feel that a Marcus-voice message is something a real coach would send them?**

We're not testing visuals. We're not testing the v2 IA. We're testing **the voice alone**, in isolation, on hand-written samples.

## Hypothesis

The Marcus voice — direct, fragmented, declarative, occasionally dry — resonates with users in the dropout-prone segment **more** than the typical AI-coach voice (warm, validating, motivational). They will:

- Recognize it as "a coach", not "an app"
- Not find it cold or harsh
- Specifically prefer it to a soft-coach control sample when shown both
- Spontaneously say things like *"that sounds like a person"* or *"that's how my old trainer used to text me"*

If 4 of 5 users react this way, the voice ships. If 2 or fewer do, we revisit the archetype.

## Method

- **Format:** 30-minute semi-structured interview, remote (Zoom/Meet) or in-person
- **N:** 5 users (small-n qualitative; we're looking for strong signal, not statistical power)
- **Compensation:** $50 gift card or equivalent
- **Recording:** with consent, for review (don't ship anything publicly)

## Recruitment criteria

Target users for this test must have **all** of:

1. Owned at least one habit/fitness/wellness app in the past 2 years
2. **Stopped using it within 30 days** (the dropout segment — exactly who we're solving for)
3. Are between 25 and 50 years old
4. Have not heard of The Coach before the interview

Mix on:

- Gender (aim for 3F/2M or 2F/3M; not 5/0)
- Whether they consider themselves "fit" or not (mix)
- Whether they have used a personal trainer in real life (at least 2 yes, at least 2 no)

## Materials

Print or screen-share three coach-voice samples + one control. **All hand-written by us, no LLM generation in the test.** Each sample is a hypothetical text message from a coach to the user — no app context, no logos.

### Sample 1 — slip-day intervention (Marcus voice)

> Two in a row. Something's getting in the way and I want to know what. Today: one set of squats at 95. That's it. Tap in after.

### Sample 2 — return after absence (Marcus voice)

> Haven't seen you in a bit. Still in?
>
> *(three buttons: Back in / Give me a week / I'm done)*

### Sample 3 — weekly letter excerpt (Marcus voice)

> Three sessions this week. First time you've hit three. The body knows.
>
> Bench held at 95 all three days. We push that Tuesday — 100, see how it sits. Squat moved 145 to 150 clean.
>
> Friday became Saturday. Counts the same. Don't get cute with it as a pattern.

### Control (soft-coach voice — the typical AI-app tone)

> Hey! I noticed you missed your last two workouts — no judgement, life happens! 🙌 Let's get back on track together. Today, try just one set of squats — even small wins count. You've got this! Trust the process. 💪

**The control is intentionally exaggerated** — but not by much. It's the actual register most AI coaching apps use today.

## Interview script

### Part 1 — context (5 min)

Open with rapport-building, then get to the dropout history:

- "Tell me about the last fitness or habit app you used."
- "How long did you stick with it?"
- "What made you stop?"
- "What did you wish it had done differently?"

Listen for: *streaks broke me, felt like work, started feeling judged, got generic, lost interest, life got busy*. These are the signals our differentiator targets.

### Part 2 — present the samples (15 min)

Don't lead. Just hand them the first sample and ask:

> "Imagine you got this message from a coach. Read it. Tell me what you think."

Let them talk. Don't define "what you think" further. After they've reacted naturally, probe:

- "Who sent this, in your imagination?"
- "How does it land?"
- "Would you reply to this? Do anything?"
- "Does this feel like a real person or like a computer?"

Repeat for samples 2 and 3. Vary order between participants (don't always show Sample 1 first).

After all three Marcus samples, show the control:

> "Now here's another one from a different coach."

Same probes. Don't telegraph which is "ours."

Then the comparison question:

> "If you had to pick — which of these coaches would you actually listen to?"

Ask why. Listen for specifics — vocabulary they cite, lines they remember, what made them prefer one over the other.

### Part 3 — debrief (10 min)

Now reveal context (still don't reveal we built it):

- "All four of those were drafts for a fitness coaching app. The first three are the same coach. The last one is the kind of voice most apps actually use."
- "Did anything in the first three feel off, harsh, or wrong?"
- "Was there anything you wished it said?"
- "Where would this voice not work — what kind of person would it not be right for?"

The last question matters — we want users to name the negative space. If a user can't think of *anyone* who'd dislike it, they're being polite. Press gently.

### Wrap

- "If a coach actually texted you the way these three did, would you keep responding to them after a week? A month?"

This is the loyalty proxy. Strong yes = the voice can survive past day-3 motivation. Hesitation = we need to revisit.

## What we listen for (signal we want)

**Strong-positive signal:**
- *"That sounds like a real person."*
- *"My old trainer used to text me like this."*
- *"I'd actually do the thing if a coach said it that way."*
- They quote a specific line back to us unprompted.
- They explicitly contrast with the control: *"the first one isn't trying to make me feel things — I appreciate that."*

**Yellow flag:**
- "It's a bit harsh." (one or two users — fine; three or more — concern)
- "Feels like a man." (if a female user perceives the voice as gendered and that bothers them; need to test more)
- Can't tell if it's a person or an AI (we wanted them to feel it was a person)

**Red flag:**
- "I'd find this rude/dismissive."
- "I'd delete the app."
- "I prefer the second one." (the control)
- "This makes me feel bad about myself."

## Decision matrix

After all 5 interviews, tally responses:

| Outcome | Action |
|---|---|
| 4 or 5 strong-positive on the comparison question | **Ship Marcus voice as designed.** Proceed with v2. |
| 3 strong-positive, no red flags | **Ship with small tonal softening** on the highest-risk surfaces (return + slip). Re-test after first 30 days of usage. |
| 2 or fewer strong-positive, OR any red flags from 2+ users | **Revise the archetype.** Likely move toward the "older brother — warmer end" calibration. Re-test before shipping. |
| Mixed signal where gender or background obviously segments responses | **The voice may need persona-by-persona calibration.** Significant rethink — possibly each user picks an archetype during onboarding. |

## What this test does NOT validate

- Visual design — we're showing text only
- Information architecture — no tabs, no flow
- Whether the brain's reasoning is good — sample texts don't reflect personalization
- Whether real *generated* output stays in-voice — the LLM pipeline is a separate eval (see `voice/pipeline.md`)
- Push notification behavior — that's a separate test (frequency, timing)

This is **voice resonance only**. One question. One answer.

## Risks of this test itself

- **Hawthorne effect** — users may say what they think we want to hear. Mitigation: don't reveal which sample is ours until the end; ask negative-shaped questions ("where would this voice not work?"); listen for hesitation and contradiction more than affirmation.
- **Sample size of 5** — small. We are looking for strong qualitative signal, not statistical proof. If results are mixed at n=5, do another 5 with the revised samples before deciding.
- **Hand-written samples ≠ LLM output** — the test validates the *direction* of the voice, not whether the LLM can actually produce it consistently. The LLM consistency test is downstream (voice pipeline eval).
- **Self-reporting future behavior** — "I'd keep responding after a month" is famously unreliable. We're asking it anyway as a proxy, but treat with skepticism.

## Timeline

- Day 1: finalize samples, recruit 5 users via UserInterviews.com or similar
- Days 2–4: schedule interviews
- Days 5–7: run interviews
- Day 8: synthesis + decision
- Day 9: voice spec revision (if needed) OR v2 engineering proceeds

Total: ~9 days end-to-end. Cheap insurance against shipping the wrong voice.

## Deliverable

A short synthesis doc (1-2 pages) with:

1. The decision (ship / soften / revise)
2. Direct quotes from users that support the decision
3. Any specific lines from the samples that landed especially well or poorly (helps refine `voice/examples.md`)
4. Patterns by demographic if any (gender, age, fitness background, prior app experience)

This synthesis goes into `design/research/01-voice-resonance-findings.md` (new file, created post-study).

## Open questions

- Should we also test a **Drill archetype** (Frisella-shaped) as a third option, to see if some users actually prefer it? Probably not in this round — we'd be running an A/B/C with n=5, which is statistically meaningless. Test Marcus vs. soft-coach control only.
- Should we recruit a separate cohort of *current 75 Hard users* to test the Drill archetype? Yes — but as a *second study*, not bundled with this one. If Marcus works for the dropout segment and Drill works for the 75 Hard segment, that's two products eventually.
- Should we test the samples on iOS-formatted screens vs. raw text? Probably raw text only — visual styling would confound voice evaluation.
