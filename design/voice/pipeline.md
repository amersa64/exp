# The two-stage pipeline

How a coach message gets generated, from "the brain has decided to say something" to "the user reads a string in coach voice."

## The shape

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│   COACH STATE + EVENT TRIGGER (scheduler tick, user log, etc.)   │
│                                                                  │
└─────────────────────────────┬────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  STAGE 1 — PLANNER                                               │
│                                                                  │
│  Reads:  full user model, program state, recent events,          │
│          calendar/HealthKit signals, persona                     │
│  Decides:                                                        │
│    - Should the coach say anything right now?  (restraint)       │
│    - If yes, what should the coach say?  (purpose + facts)       │
│  Output:  structured INTENT object (JSON)                        │
│  Voice:   AI's normal voice. Internal only. Never user-visible.  │
└─────────────────────────────┬────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  STAGE 2 — VOICE TRANSFORMER                                     │
│                                                                  │
│  Reads:  the INTENT, the voice-spec, the archetype, 3-5 matching │
│          examples from examples.md                               │
│  Produces: user-facing string in coach voice                     │
│  Validates: denylist regex, length cap, punctuation,             │
│             aloud-test (LLM judge)                               │
│  Regenerates on failure (max 2 retries), then falls back to a    │
│  hand-authored string from examples.md.                          │
└─────────────────────────────┬────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  DELIVERY                                                        │
│                                                                  │
│  APNs push, or in-app card render, or weekly letter screen.      │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

## Why two stages

A single LLM call that does both planning and voicing has two failure modes that destroy this product:

1. **Voice drift.** Each generation re-derives the voice from scratch. Even with a strong system prompt, output drifts toward the model's general "helpful coach" default — exactly the AI-slop voice we are fighting. Two stages let the voice transformer be a *narrow specialist* that only has to nail tone.
2. **Untestable separation.** "Did the coach reason well?" and "Did the coach sound right?" are different questions with different fixes. One stage conflates them; two stages let us regress-test them independently.

The separation also lets us **swap archetypes** for A/B testing or for market segments without touching planning logic. The drill-instructor and older-brother versions of the same intent are different voice-stage prompts, same planner output.

## The intent schema (Stage 1 output)

Stage 1 always produces a JSON object of this shape:

```json
{
  "surface": "coach-tab-shape-B",
  "purpose": "prescription delivery",
  "facts": [
    "session = Full A",
    "squat moves 145 → 150",
    "bench holds at 95",
    "anchor = morning coffee",
    "location = garage"
  ],
  "instruction": "warm up properly on squat; first set will feel heavy",
  "tone_target": "base",
  "max_words": 35,
  "context_for_voice": {
    "user_recent_sessions": 2,
    "last_skip_was": null,
    "weekly_letter_due": false
  }
}
```

### Required keys

- `surface` — which UI surface this is for. Determines which examples in `examples.md` are loaded as few-shot.
- `purpose` — one short phrase, ≤6 words.
- `facts` — list of plain-language statements. **These are the only inputs the voice transformer is allowed to use.** It cannot invent numbers, lifts, dates, or events that aren't in `facts`.
- `tone_target` — one of: `base`, `slightly-sharper`, `slightly-warmer`, `out-of-lane-refusal`. (See `voice-spec.md` § Tone calibration.)
- `max_words` — the surface cap from `voice-spec.md`.

### Optional keys

- `instruction` — if the coach should tell the user to do something specific, name it here.
- `context_for_voice` — non-fact context that influences register but doesn't get spoken (e.g. "this is the user's first slip" → warmer; "third slip this month" → sharper).
- `forbid` — list of additional phrases to avoid in this specific generation, on top of the global denylist. Used when the user-facing context makes a generally-fine phrase wrong here.

## Restraint gate (Stage 1 only)

Before Stage 1 produces an intent, it runs the existing restraint logic (`coach/nudge.py`):

- Is the user within daily cap?
- Is the cooldown elapsed?
- Has variety guard rejected the candidate?
- Is the user paused?

**If restraint says no, Stage 2 is never called.** Silence is the output, not a generated string. This is critical — generating then suppressing wastes tokens and risks the suppressed text leaking via logs or tests. Restraint comes first.

## Stage 2 prompt structure

The voice transformer's prompt is:

```
SYSTEM:
  {archetype.md compact form}
  {voice-spec.md compact form, including denylist}

  You receive a structured intent. Produce one user-facing message
  in the voice described above. Use only the facts provided.
  Do not invent details. Respect the max_words cap.

USER:
  Surface: {intent.surface}
  Purpose: {intent.purpose}
  Tone: {intent.tone_target}
  Max words: {intent.max_words}
  Facts:
    - {fact 1}
    - {fact 2}
    ...
  Instruction: {intent.instruction or "none"}

  Here are 3 examples of this character speaking in similar situations:

  Example 1 — {similar surface}:
    Intent: {paraphrased intent}
    Output: "{coach voice example}"

  Example 2 — ...
  Example 3 — ...

  Now write the message for the intent above. One message only.
  No prefix. No quotation marks around the output.

ASSISTANT:
```

## Validation (post-Stage 2)

Every generated string runs through:

```python
def validate(message: str, surface: SurfaceType) -> ValidationResult:
    if word_count(message) > MAX_WORDS[surface]:
        return Fail("over length cap")

    for phrase in DENYLIST_PHRASES:
        if phrase.lower() in message.lower():
            return Fail(f"contains forbidden phrase: {phrase!r}")

    for pattern in DENYLIST_REGEXES:
        if pattern.search(message):
            return Fail(f"matches forbidden pattern: {pattern.pattern}")

    if "!" in message and not is_sarcastic_exclamation(message):
        return Fail("sincere exclamation point")

    if ";" in message:
        return Fail("semicolon")

    if "..." in message or "…" in message:
        return Fail("ellipsis")

    if has_emoji(message):
        return Fail("emoji")

    if not aloud_test_passes(message):  # LLM judge
        return Fail("aloud test failed")

    return Pass()
```

The aloud test is a second tiny LLM call:

```
SYSTEM: You are checking whether a message sounds like a real strength
coach in a small-town gym, or like an AI pretending to be one.

USER: "{message}"

Reply with one line: PASS or FAIL: {one short reason}.
```

This is cheap (a few hundred tokens) and catches register drift the regex denylist misses. The judge model can be smaller/cheaper than the generator.

## Failure cascade

```
generation attempt 1  →  validate  →  PASS  →  ship
                                  →  FAIL  →  generation attempt 2 with the failure reason in the prompt as "avoid: X"
                                                                 →  validate  →  PASS  →  ship
                                                                              →  FAIL  →  fall back to hand-authored string from examples.md for this surface
                                                                                       →  log the failure for prompt improvement
```

The fallback bank is the **Fallback:** entries in `examples.md`. They're deliberately bland — a fallback that fails is invisible; a fallback that overclaims would be a brand-damaging surprise.

## Caching

The voice spec, archetype, and example bank rarely change. They are loaded once at process start and held in memory. Only the intent and the 3-5 matching examples vary per request.

The intent → message generation should be cached by intent hash for short-term re-generation (e.g. if the user retries a failed APNs delivery within 1 minute, reuse the cached string — don't re-generate, in case the new generation drifts from the one already promised).

## Where this lives in the backend

Proposed file structure (extending the existing `backend/coach/`):

```
backend/coach/
  voice/
    __init__.py
    archetype.py         # the archetype.md content as a constant
    spec.py              # the voice-spec.md rules as data: ALLOWLIST, DENYLIST, REGEXES, MAX_WORDS
    examples.py          # the examples.md corpus, indexed by surface
    planner.py           # Stage 1: produces Intent objects
    transformer.py       # Stage 2: produces strings; calls Anthropic SDK; validates
    validator.py         # the regex + aloud judge
    fallbacks.py         # the hand-authored strings by surface
  nudge.py               # existing — calls voice.planner.intent_for() + voice.transformer.render()
```

The existing `coach/variety.py` (structural variety guard) operates on the *output strings* — i.e. it runs **after** Stage 2 succeeds. A near-duplicate of yesterday's coach voice triggers a re-roll of Stage 2 with explicit avoid-this guidance.

## Eval set (for regression testing)

A directory of test cases:

```
backend/coach/voice/evals/
  prescription/
    case_001.json     # intent + expected sample + 5 acceptable alternates
    case_001.bad.json # an intent + a string that must fail validation
  slip/
    case_001.json
    ...
  return/
    case_001.json
    ...
```

Each case has a (intent → acceptable outputs) pair, OR (intent + bad_output → expected validation failure). 30 cases at launch is enough. Run the eval before every prompt change. If the pass rate drops, the change is bad.

## What this pipeline does NOT solve

- **The planner getting the facts wrong.** If Stage 1 thinks the user squatted 150 when they actually squatted 145, Stage 2 will faithfully translate the wrong number into perfect coach voice. The voice layer trusts the planner. Garbage in, well-spoken garbage out.
- **Whether the coach should speak at all.** That's the restraint gate, upstream of the planner. Silence is always a legitimate output.
- **Static UI strings** (button labels, navigation titles). Those are product chrome, written by hand, not generated.
- **The user's own text echoed back.** When the user types a friction note, the coach quotes/echoes their phrasing in the next message even if it breaks our rules. Their words, his voice.

## A note on the order we implement this

If you're shipping voice incrementally:

1. **First**: hand-author the surfaces in `examples.md` as static strings and use them directly in the iOS app. No LLM. Test whether the *voice itself* lands with users.
2. **Then**: add Stage 2 (voice transformer) for the planner outputs that already exist (nudge text). Keep Stage 1 minimal.
3. **Then**: add validation + aloud judge.
4. **Last**: full Stage 1 reasoning over all signals (calendar, HealthKit, weekly cadence).

Most of the brand risk is in Stage 2 quality. Most of the product depth is in Stage 1 quality. They can be improved independently — which is the whole point of the architecture.
