# 07 — Nudge Reply sheet (v2)

The one-tap reply surface, in coach voice, with the nudge context restored.

## Role

Spec §7.3 / Rubric D5. This sheet lands from APNs push or a follow-up tap on the Coach tab. **What's new in v2**: the footer copy under each outcome is rewritten in older-brother voice (see voice spec § 9), the nudge headline is shown at the top for context, and after sending the user gets a "see what's next" deep-link to the Now tab.

## What changed from v1

| | v1 | v2 |
|---|---|---|
| Outcome footers (5 strings) | Verbose, slightly therapy-tinged | **Rewritten in Marcus voice** — see voice spec § 9 |
| Nudge context shown | No (user had to remember what they were replying to) | **Yes** — nudge headline + body fragment at the top |
| Send failure | Inline rose banner | Preserved |
| Coach response after send | Rendered well | Preserved |
| Ripples + adaptation | Rendered well | Preserved |
| Done dismiss | Returns to previous screen | Preserved, but **also offers "see what's next" deep-link to Now** |
| Outcome options | 5 (Done / Partial / Not now / Busy / Skipped) | Preserved — still 5 |

## Wireframe — pre-send (with nudge context)

```
┌─────────────────────────────┐
│ Cancel    Quick reply       │
├─────────────────────────────┤
│                             │
│ ┌─── glass ────────────────┐│  ← NEW: nudge recap
│ │ From 2h ago               ││     so user knows what
│ │                            ││     they're replying to
│ │ "Full B was on for 7:30.   ││
│ │ Bench, deadlift, pull.     ││
│ │ Still time."               ││
│ └──────────────────────────┘ │
│                             │
│ ┌─── glass ────────────────┐│
│ │ HOW DID IT GO?            ││
│ │                            ││
│ │ [Done|Partial|Not now|     ││  ← segmented picker
│ │  Busy|Skipped]              ││     (Done pre-selected
│ │                            ││      from APNs action)
│ │ Counts. World grows.       ││  ← coach-voice footer
│ │                            ││     updates per outcome
│ └──────────────────────────┘ │
│                             │
│ ┌─── glass ────────────────┐│
│ │ FRICTION NOTE              ││
│ │ ┌──────────────────────┐  ││
│ │ │ e.g. kids meltdown   │  ││  ← same fix as 06
│ │ │ at 6pm               │  ││
│ │ └──────────────────────┘  ││
│ │ Feeds adaptation.          ││
│ └──────────────────────────┘ │
│                             │
│ [        Send         ]     │
└─────────────────────────────┘
```

## The 5 outcome footers — rewritten

These come straight from the voice spec § 9. They are the **only** lines on the sheet that the user reads as the coach's voice in the pre-send state, so they have to land.

| Outcome | v2 footer |
|---|---|
| Done | Counts. World grows. |
| Partial | Holds the load. No add Thursday. |
| Not now | Trying you again later today. |
| Busy | Done for today. Picking it up tomorrow. |
| Skipped | Logged. See you tomorrow. |

Each is a single line, generally 4-7 words. Outcome-aware — the line under the picker updates as the user changes selection. **No exclamation points. No reassurance theater. No "we all need rest sometimes."**

### v1 → v2 footer diff (full)

| Outcome | v1 string | v2 string | Reason for change |
|---|---|---|---|
| Done | "Counts as a verified vote. The world grows." | "Counts. World grows." | "verified vote" is engineer-speak; tightened |
| Partial | "Holds the load — no progression, no punishment." | "Holds the load. No add Thursday." | em-dash + "no punishment" reassurance theater; replaced with specific next-action ("no add Thursday") |
| Not now | "Coach will back off and try again later." | "Trying you again later today." | third-person; first-person is more relational |
| Busy | "Acknowledged. No retry today." | "Done for today. Picking it up tomorrow." | "acknowledged" is system-voice |
| Skipped | "Logged. No judgement — life happens." | "Logged. See you tomorrow." | "no judgement" + "life happens" are denylist phrases |

## Nudge recap at top — the new context card

The card at the top shows enough of the original nudge that the user remembers what they're answering. It includes:

- **"From {N}h ago"** — relative time stamp
- **A quoted excerpt** of the nudge (the headline + body, ~25 words max)

The quote uses *italicized serif* to differentiate the past coach message from the present sheet UI. Not "as the coach would say it now," but "as the coach said it then" — a quote.

Why we added this: in v1, a user who tapped a push from a nudge they got earlier might not remember which nudge it was. The reply sheet asked "how did it go?" without context. That's annoying. The recap fixes it.

## Wireframe — post-send (success)

```
┌─────────────────────────────┐
│ Done    Quick reply         │
├─────────────────────────────┤
│ (nudge recap + form, faded) │
│                             │
│ ┌─── tinted ember ────────┐ │
│ │ FROM YOUR COACH 〝       │ │  ← coach response
│ │ Clean. Squat goes to    │ │
│ │ 155 Thursday — same     │ │
│ │ script.                 │ │
│ └─────────────────────────┘ │
│                             │
│ ┌─── glass ───────────────┐ │
│ │ REFLECTED IN YOUR WORLD  │ │
│ │ ✨ +7 effort              │ │
│ │ ✨ 27 votes               │ │
│ └─────────────────────────┘ │
│                             │
│ [   See what's next     ]   │  ← NEW deep-link
│ [·       Done         ·]    │
└─────────────────────────────┘
```

After send:
- **Cancel → Done** (top-left)
- Form fields fade
- Coach response card appears (tinted ember — it's the coach speaking)
- Ripples card appears (glass — it's the world reflecting)
- Two CTAs: primary "See what's next" → deep-links to Now tab with the (just-adapted) prescription; secondary Done → dismiss back to wherever.

## Wireframe — post-send (failure)

```
│ (form remains editable)     │
│                             │
│ ┌─── tinted rose ─────────┐ │
│ │ ⚠ Couldn't send.        │ │
│ │   Try again.            │ │
│ └─────────────────────────┘ │
│                             │
│ [        Send         ]     │  ← re-enabled
```

Same pattern as the in-app Log Session sheet. Inline error, sheet stays open, user can retry or cancel.

## Entry points

1. **APNs push tap** — `UNNotificationResponse` → `NudgeReplyRouter.present()`. The push includes the nudge id; the sheet fetches the recap from `GET /nudges/{id}`.
2. **Follow-up card tap on Coach tab** — sheet opens with the corresponding nudge id already known.
3. **(Future)** Apple Watch reply — probably routes through the same backend reply endpoint without opening this sheet.

## Exit paths

- **Cancel** (pre-send) → dismiss, no state change
- **Done** (post-send) → dismiss to previous screen
- **See what's next** (post-send) → dismiss + programmatically switch to Now tab
- Sheet swipe-down dismisses at any time; if mid-reply, no state is saved
- After dismiss, the parent surface refreshes (Coach tab re-renders; the just-cleared follow-up disappears)

## Apple Watch / lock-screen actions

Out of scope for v2 spec, but a note for the future: the APNs notification can carry up to four quick actions. Today they correspond to outcome categories. The right four are probably:

- ✓ Done
- ▲ Partial
- ◯ Later
- ✗ Skip

These would let a user clear the loop without opening the app — exactly the spec §1 "useful without opening" north star. The reply sheet only opens if the user wants to add a friction note. v2 doesn't require this; v2.1 should.

## States

| State | Trigger | Visual |
|---|---|---|
| Idle | Sheet opens, nudge recap loaded | Recap card + form + Send |
| Loading recap | Sheet opens, recap fetching | Recap card shows ProgressView |
| Recap failed | Recap fetch errored | Recap card shows fallback text: *"Replying to your last nudge"* — still let user proceed |
| Sending | Send tapped | Send shows spinner; form disabled |
| Sent (success) | Backend returned | Form faded; coach + ripples; two CTAs |
| Sent (failure) | Backend errored | Form re-enabled; rose banner |

## Engineering notes

- **Recap endpoint** — needs `GET /nudges/{id}` returning at least `headline`, `body`, `fired_at`. If the endpoint doesn't exist yet (it likely doesn't on the FastAPI side), add it. Small.
- **Coach response field** — already returned by `POST /nudges/{id}/reply`. Rendering same as today.
- **Tab switching from sheet dismiss callback** — requires the parent tab's selection binding to be passed down to the sheet, same as the Log Session sheet fix in `06-log-session-v2.md`.

## Open questions

- Should the recap card be tappable to expand the full nudge? Probably no — keep the sheet focused. If a user wants the full text they can drag down to see the Coach tab's history (in v2.1 with letter archive).
- Should "Done" outcome immediately offer a Watch-shaped quick-confirm (haptic + dismiss without showing the form), assuming most Done replies have no friction note? Maybe — but it's a v2.1 polish, not v2 core.
- Should there be a "Mark all caught up" shortcut for users who have multiple unanswered nudges? Probably no — replying to each is the relationship contract. We don't bulk-clear.
