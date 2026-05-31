# The Coach — voice

The voice is the product. The coach's logic, prescriptions, milestones, and the entire growing world can be perfect — and if the coach *sounds like an AI*, none of it lands. This directory is the contract that prevents that.

## The architectural rule

The coach speaks in two stages:

```
┌─────────────────────┐      ┌─────────────────────┐
│  Stage 1: PLANNER   │      │ Stage 2: VOICE      │
│                     │      │                     │
│  Decides WHAT to    │ ───► │  Decides HOW the    │
│  say. Uses AI voice │      │  coach says it.     │
│  internally. Outputs│      │  Reads the spec +   │
│  structured intent. │      │  examples. Outputs  │
│                     │      │  user-facing text.  │
└─────────────────────┘      └─────────────────────┘
```

The planner is allowed to think in AI voice. The voice transformer is the only thing the user sees, and it is bound by `voice-spec.md`. **The user must never see the planner's output directly.** That's the line.

See [`pipeline.md`](pipeline.md) for the implementation.

## The character

We picked one archetype: **the older brother**. Direct, dry, supportive, not soft. A specific 38-year-old strength coach from a small town. He has a name internally (so the LLM has a person to imitate); the user never sees the name.

See [`archetype.md`](archetype.md) for the full brief.

## The rules

Hard constraints on what the voice can and cannot say. Allowlist, denylist, sentence shape, punctuation, length caps. These are stuffed verbatim into the voice transformer's system prompt, and they're also enforced as a post-generation refusal check.

See [`voice-spec.md`](voice-spec.md).

## The examples

For every surface in the app — welcome, intake, prescription, slip, return, weekly letter — there is a paired example: the underlying intent in AI voice, and the coach's spoken version. This is the few-shot corpus the voice transformer reads.

See [`examples.md`](examples.md).

## Reading order

If you are…

- **A product/design person sanity-checking the voice** → read [`archetype.md`](archetype.md) then skim [`examples.md`](examples.md). That's the experience.
- **An engineer wiring this into the backend** → read [`pipeline.md`](pipeline.md), then [`voice-spec.md`](voice-spec.md). The first is the architecture; the second is the contract.
- **An LLM prompt author** → read all four in order. All four go into the prompt.

## The one rule above all others

> If a generated message would not survive being read aloud by a real strength coach in a small-town gym at 5am, it does not ship.

The denylist is downstream of that rule. The archetype is downstream of that rule. Every decision in this directory points back to that sentence.
