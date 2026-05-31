# 09 — Nudge Reply (modal sheet)

The one-tap reply surface for a nudge. Lands from APNs push or a follow-up card.

## Role

Spec §7.3 / Rubric D5 — "one-tap reply loop". This is **not a dashboard**. The default outcome is pre-selected from the notification action so the user can confirm with a single tap. Friction note is optional. After send, the coach speaks back.

This sheet is the linchpin of push-not-pull (§C1): the coach can fire a nudge while the phone is in the user's pocket, and the user can resolve it without ever opening the app fully. The reply sheet IS the app for that interaction.

## Wireframe — opened (pre-send)

```
┌─────────────────────────────┐
│ Cancel    Quick reply       │
├─────────────────────────────┤
│ ┌─────────────────────────┐ │
│ │ HOW DID IT GO?          │ │  ← eyebrow
│ │                          │ │
│ │ [Done|Partial|Not now|   │ │  ← 5-segment picker
│ │  Busy|Skipped]            │ │     pre-selected from APNs
│ │   (Done selected)        │ │
│ │                          │ │
│ │ Counts as a verified     │ │  ← outcome-dependent footer
│ │ vote. The world grows.   │ │     (changes with selection)
│ └─────────────────────────┘ │
│                             │
│ ┌─────────────────────────┐ │
│ │ FRICTION NOTE           │ │
│ │ ┌─────────────────────┐ │ │
│ │ │ What got in the     │ │ │
│ │ │ way? (optional)     │ │ │
│ │ └─────────────────────┘ │ │
│ │ Feeds adaptation.       │ │
│ │ Specific beats polite — │ │
│ │ "kids meltdown at 6pm"  │ │
│ │ is more useful than     │ │
│ │ "busy".                 │ │
│ └─────────────────────────┘ │
│                             │
│ [        Send         ]     │  ← ember cta
└─────────────────────────────┘
```

## Wireframe — after send (success)

The Cancel button changes to **Done**. The result cards appear above the (now-disabled) Send button:

```
┌─────────────────────────────┐
│ Done    Quick reply         │  ← cancel renamed to Done
├─────────────────────────────┤
│ ┌─── outcome card (above) ┐ │
│ │                          │ │
│ │ ┌── friction card ─────┐ │ │
│ │                          │ │
│ │ ┌─── tinted ember ────┐  │ │  ← coach voice
│ │ │ FROM YOUR COACH 〝   │  │ │
│ │ │ 👤? "Three Mondays in │  │ │
│ │ │      a row. Quiet     │  │ │
│ │ │      proof."          │  │ │
│ │ └─────────────────────┘  │ │
│ │                          │ │
│ │ ┌── glass ─────────────┐ │ │  ← world ripples
│ │ │ REFLECTED IN YOUR     │ │ │
│ │ │ WORLD ✨              │ │ │
│ │ │ ✨ +7 effort           │ │ │
│ │ │ ✨ streak: 3 days      │ │ │
│ │ │ ✨ living system       │ │ │
│ │ │   thriving             │ │ │
│ │ │                       │ │ │
│ │ │ Next session: +5 lb   │ │ │  ← adaptation rationale
│ │ │ on squat.             │ │ │
│ │ └─────────────────────┘ │ │
│ │                          │ │
│ │ [ Send (disabled, faded)]│ │
│ └──────────────────────────┘ │
└─────────────────────────────┘
```

## Wireframe — after send (failure)

```
│ ┌─── tinted rose ─────────┐ │
│ │ ⚠ {error.localizedDescr} │ │  ← rose-tinted error card
│ └─────────────────────────┘ │
│ [ Send (re-enabled)        ]│
```

## The five outcomes

| Outcome | Footer copy | Brain action |
|---|---|---|
| **Done** | "Counts as a verified vote. The world grows." | grow world, advance progression |
| **Partial** | "Holds the load — no progression, no punishment." | log, hold |
| **Not now** | "Coach will back off and try again later." | reschedule attempt, no penalty |
| **Busy** | "Acknowledged. No retry today." | suppress further attempts today |
| **Skipped** | "Logged. No judgement — life happens." | back-off curve applies |

The footer is **outcome-aware** — changing the picker changes the explanation. This is small but tonally important — the coach is telling the user "I heard you" *in advance* of the send.

## Content states

| State | Trigger | Visual |
|---|---|---|
| Idle | Sheet opened from APNs/follow-up | form + Send |
| Sending | Send tapped | "Sending…" + spinner inline |
| Sent (success) | Backend returned ripples + coach response | result cards above disabled Send; Cancel → Done |
| Sent (failure) | Network or 5xx | rose-tinted error card; Send re-enabled |

## Enters from

- **APNs nudge tap** — `UNNotificationResponse` → `NudgeReplyRouter.present()` → sheet
- **Today tab → follow-up card** — `.sheet(item:)` from `FollowupsSection`

## Exits to

- **Cancel** (pre-send) → dismiss with no change
- **Done** (post-send) → dismiss
- Sheet swipe-down dismisses at any time
- If entered from Today tab: parent tab refreshes on dismiss (so the follow-up disappears from the list)
- If entered from APNs: returns to whatever was on screen (could be any tab, or the lock screen if app was backgrounded)

## UX questions

- **Five outcomes is a lot for "one-tap reply".** The spec wants one tap. Five segments is closer to four taps (decide which segment, then send). Could the APNs notification expose three actions (Done / Partial / Skipped) and the sheet only opens for the latter two? Today the sheet always opens.
- **Not now vs Busy is a confusing distinction** for most users. The semantics diverge in the brain (retry vs no-retry today) but the words don't make that obvious. Worth rephrasing as "Later today" / "Not today".
- **The coach's voice ("FROM YOUR COACH") is the most powerful UX moment in the app.** It only appears here. Worth making sure it appears in `LogSessionSheet` too — currently it doesn't (see `04-train-log-session.md`).
- **Result state is dismissible-only.** After seeing the ripples + coach voice, the only action is Done → dismiss. Could there be a "What's next?" CTA inline that opens the Train tab to the just-adapted prescription?
- **Friction note placeholder is text, but encouragement is in the caption.** "What got in the way? (optional)" is in the field; "Specific beats polite" is below. A user who reads the placeholder and not the caption types "busy" — exactly what the caption is warning against. Could the placeholder *be* the caption: "e.g. kids meltdown at 6pm"?
- **APNs delivers a `userInfo["nudge_id"]` but doesn't carry a snapshot of the nudge itself.** The reply sheet shows no context — no "this is the reply to Tuesday's lift". The user has to remember what they're replying to. Worth surfacing the nudge headline at the top of the sheet.
- **No deep-link after send.** A successful Done could deep-link to Train tab to show the next session. Today, dismiss returns to the previous screen — which may be the lock screen.
