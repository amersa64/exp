# 04 — Weekly Letter

A single screen, surfaced once a week. The artifact people screenshot and share. The thing no tracker can produce.

## Role

The weekly letter is the **brand-defining ritual**. Once a week — Sunday at 18:00 local time — the coach sends a letter. It's short (200-220 words max). It's specific to the user (every fact in it is something that actually happened). It's signed *— Coach*. It opens full-screen, no tab bar. It is, by a large margin, the most carefully-typeset surface in the app.

Why it matters: an app that produces a letter you'd screenshot stops being an app. It becomes a *relationship artifact*. That's the difference between a tracker and a coach in pocket. Tracker = "you logged 27 sessions." Coach = a letter you can read and feel addressed by.

## When the user encounters it

Two paths:

1. **Push notification** — Sunday 18:00 local: *"Sunday — your week."* Tap → opens letter directly.
2. **Coach tab card** — From Sunday morning through Wednesday end-of-day, the Coach tab shows a small card above the main shape:
   ```
   ┌─────────────────────────┐
   │ 📜 This week's letter   │
   │                         │
   │ Three sessions. Bench   │
   │ moved. Open it.    ›    │
   └─────────────────────────┘
   ```
   After Wednesday the card disappears. The letter is then archived to Becoming tab → "Past letters" (a v2.1 feature; not in v2).

## Wireframe

```
┌─────────────────────────────┐
│ ✕  (close)                  │  ← top-right close
├─────────────────────────────┤
│                             │
│ SUNDAY — WEEK 3             │  ← small eyebrow
│                             │
│                             │
│ Three sessions this         │  ← body (serif, generous
│ week. First time you've     │     leading, 18pt)
│ hit three. The body         │
│ knows.                      │
│                             │
│ Bench held at 95 all        │
│ three days. We push         │
│ that Tuesday — 100, see     │
│ how it sits. Squat moved    │
│ 145 to 150 clean.           │
│                             │
│ Friday became Saturday.     │
│ Counts the same. Don't      │
│ get cute with it as a       │
│ pattern.                    │
│                             │
│ Next week: row volume       │
│ goes up. Back can take it.  │
│                             │
│ Sleep.                      │
│                             │
│                             │
│ — Coach                     │  ← signoff
│                             │
│                             │
│ ┌─────────────────────────┐ │
│ │     Save to photos      │ │  ← primary CTA
│ └─────────────────────────┘ │
│                             │
│ ┌─────────────────────────┐ │
│ │ ·     Share          ·  │ │  ← ghost
│ └─────────────────────────┘ │
│                             │
└─────────────────────────────┘
```

## Typographic detail

This screen, alone in the app, gets specific typography:

- **Body text:** serif (matches the Identity statement font choice), 18pt, line-height 1.5
- **Eyebrow ("SUNDAY — WEEK 3"):** all-caps, tight tracking, muted color, 11pt
- **Signoff:** italic serif, 17pt, full opacity
- **Background:** the standard `AtmosphericBackground()` but with a slight vignette so the text feels like a letter laid on the world
- **Width:** centered, max ~320pt width on iPhone — letter-shaped, not edge-to-edge

The aesthetic target: handwritten note > tracker summary. People take screenshots of well-typeset things.

## Content structure

Every letter follows the same skeleton, filled by the planner with that week's facts. The voice transformer renders each section:

```
1. Opening fact about the week           ← "Three sessions this week."
2. One specific achievement, in numbers  ← "Bench held at 95…"
3. One specific friction, acknowledged   ← "Friday became Saturday."
4. One forecast for next week            ← "Next week: row volume goes up."
5. Closing imperative or single word     ← "Sleep."
6. Signoff                                ← "— Coach"
```

5 paragraphs + signoff. Max ~220 words. Most letters will be 150-180 words.

> Some weeks the planner won't have content for slot 3 (no friction worth noting) or slot 4 (no change planned). The voice transformer is allowed to omit slots. Empty paragraphs are fine. **The letter is allowed to be short.** A 4-sentence letter is more powerful than a 10-sentence one if the 4 sentences are the right ones.

## Slip-week letter (special case)

When the user had a bad week — 0 or 1 sessions — the letter changes register slightly. Same structure, sharper opening:

```
SUNDAY — WEEK 3

This week was 1.

Tuesday's bench got done. The rest 
didn't. Work or body or both — I 
don't know yet.

Next week: same program. We don't 
restart, we don't deload. We just 
go again.

Get to sleep early Sunday.

— Coach
```

Notice what the slip-week letter doesn't do:
- ❌ Apologize for the user ("I know it was a tough week")
- ❌ Add motivational filler ("you've got this")
- ❌ Soften the count ("you did your best")
- ❌ Reframe the failure as success ("rest is part of progress")

It acknowledges, instructs, and signs off. That's the contract.

## Save to Photos — the screenshot ritual

The "Save to Photos" CTA renders the letter to a 1080×1920 image with the same typography, plus a subtle bottom watermark: *"the coach · sundays"*. Saves to the user's camera roll.

Why this matters: people **share screenshots of things they're proud of**. A letter that calls out their specific achievement, in legible warm typography, with a coach signoff — that's a shareable artifact. The watermark is the marketing. Subtle, not promotional. Functions like a publication's sign-off.

## Share CTA

Standard iOS share sheet with the saved image. Lets the user post directly to Instagram, send to a friend, etc. We don't engineer share-to-X — we just hand iOS the image and let the OS do its thing.

## What this screen is not

- **Not editable.** The user does not write to or annotate the letter. It's from the coach.
- **Not a chat.** There is no reply field. The letter is one direction. The coach speaks; the user reads.
- **Not gamified.** No "share this for points" or "send to 3 friends to unlock." The share is voluntary and unrewarded by the app. Real coaches don't ask you to post about them.
- **Not skippable.** The push notification can be dismissed, but the letter sits on the Coach tab for ~4 days. If the user genuinely doesn't open it, that's information for the brain (declining engagement), not punishment for the user.

## States

| State | Trigger | Visual |
|---|---|---|
| Loading | Letter being generated server-side on first view | Centered spinner, no content |
| Ready | Generation succeeded | Letter rendered |
| Failed | Generation failed twice and fallback also failed | Empty state: *"No letter this week. The coach took the night off."* — playful but in-voice |
| First weekly letter ever | Week 1 of the program | Header changes to "WEEK 1 — FIRST LETTER" |

## Generation pipeline (engineering note)

The letter goes through the standard two-stage voice pipeline (`../../voice/pipeline.md`) but with a few specifics:

1. **Planner input:** the week's `VerifiedEvent`s, the program adaptations, the LLM observations from the journal, the milestone deltas.
2. **Planner output:** an intent with `surface: "weekly-letter"` and 4-5 facts ordered by importance.
3. **Voice transformer:** renders against the letter template + 3 examples from `examples.md` § 12.
4. **Validation:** standard voice spec + length cap (220 words) + a domain check ("does the letter reference facts not in the input?" — refuse hallucinated specifics).
5. **Caching:** once generated, the letter is **frozen for the week**. Re-renders return the same string. The letter is a fact about that week, not a regeneration target.

Generation happens server-side on the cron tick that fires the push. The iOS app fetches it via `GET /letters/current` and renders.

## Risks

- **Generic letters.** If the planner doesn't have enough specific facts to populate the slots, the letter will read generic, which is worse than no letter. Mitigation: refuse to generate a letter when fewer than 1 verified event occurred that week — fall through to a minimal "no letter this week" state. Don't paper over emptiness.
- **Voice drift.** The letter is the longest single piece of generated content in the app. Drift accumulates over 200 words. Mitigation: hand-validate the first 10-20 real letters generated for real users; flag any that read off-voice; tune the prompt.
- **Hallucinated specifics.** A letter that says "your squat went from 145 to 150" when the squat actually went from 145 to 150 is the magic. A letter that says it went to 155 when it didn't is a brand-killer. The validation step must check every numerical claim against the source facts.
- **Sunday 18:00 may be wrong for some users.** Global time-zone handling required. Push fires per user's local timezone. Configurable in Settings later (not v2).

## Open questions

- Should the letter include the identity statement somewhere — as a tie-back to who they said they wanted to become? Probably no — repetition would dilute it. The letter implies the identity by talking about specific actions. Showing the statement explicitly would feel like a coach recap of a coach prior session.
- Should there be a way for the user to **respond** to the letter? Argument for: closing the loop. Argument against: the letter is a monologue, deliberately. **No reply field. Decided.** If the user wants to reply, they have all week of Coach-tab interactions.
- Plain-text share vs. image share — should we offer both? Image only for v2. Plain text feels less like an artifact. Test image-only with real users before adding text option.
