# 06 — Log Session sheet (v2)

The in-app report path. Fixes three v1 issues — silent failure on send, missing coach response, generic friction placeholder.

## Role

Same job as v1: REPORT step of the loop. The user logs done / partial / skipped + an optional friction note. Backend records a `VerifiedEvent` and the brain adapts the next session. **What's new in v2** is that the *coach speaks back inline before the sheet dismisses* — currently a bug where the coach's response (`coachResponse` field on the API) is rendered in the APNs reply path but silently dropped in this sheet.

## What changed from v1

| | v1 | v2 |
|---|---|---|
| Outcome options | Done / Partial / Skipped | Same |
| Friction placeholder | "What got in the way? (optional)" | **"e.g. kids meltdown at 6pm"** — example as placeholder |
| Coach response after send | Not rendered (bug) | **Rendered inline, on the same sheet, before dismiss** |
| Failure handling | Sheet dismisses silently on 4xx/5xx | **Sheet stays open with inline error; Send button re-enables** |
| Result UI | Sheet dismisses → ripples banner on Now tab | **Sheet shows coach response + ripples in-sheet; user taps Done to dismiss; Now tab still gets banner for redundancy** |

## Wireframe — pre-send

```
┌─────────────────────────────┐
│ Cancel     Log session      │
├─────────────────────────────┤
│ ┌─────────────────────────┐ │
│ │ FULL A                  │ │  ← eyebrow with session
│ │                          │ │
│ │ How did it go?          │ │  ← Marcus voice (audit)
│ │                          │ │
│ │ [ Done | Partial | Skip ]│ │  ← segmented picker
│ │  (Done selected)         │ │
│ └─────────────────────────┘ │
│                             │
│ ┌─────────────────────────┐ │
│ │ FRICTION NOTE            │ │
│ │ ┌─────────────────────┐ │ │
│ │ │ e.g. kids meltdown  │ │ │  ← placeholder = example
│ │ │ at 6pm              │ │ │
│ │ └─────────────────────┘ │ │
│ │ Feeds adaptation.       │ │  ← short caption
│ └─────────────────────────┘ │
│                             │
│ [        Send         ]     │  ← ember
└─────────────────────────────┘
```

## Wireframe — post-send (success)

The sheet does NOT dismiss. Instead, the form fields fade and a new section appears above the (now disabled) Send button:

```
┌─────────────────────────────┐
│ Done   Log session          │  ← Cancel → Done
├─────────────────────────────┤
│ ┌─── form ─ disabled ─────┐ │  ← outcome + friction
│ │ (faded, read-only)      │ │     visible but greyed
│ └─────────────────────────┘ │
│                             │
│ ┌─── tinted ember ────────┐ │
│ │ FROM YOUR COACH 〝       │ │  ← coach response
│ │                          │ │     (the key fix)
│ │ Clean. Squat goes to 155 │ │
│ │ Thursday — same script.  │ │
│ └─────────────────────────┘ │
│                             │
│ ┌─── glass ───────────────┐ │
│ │ REFLECTED IN YOUR WORLD  │ │  ← ripples
│ │ ✨ +7 effort              │ │
│ │ ✨ 27 votes               │ │
│ │ ✨ living system thriving │ │
│ └─────────────────────────┘ │
│                             │
│ ┌─────────────────────────┐ │
│ │  See what's next        │ │  ← NEW CTA — opens Now
│ └─────────────────────────┘ │
│ ┌─────────────────────────┐ │
│ │ ·       Done         ·  │ │
│ └─────────────────────────┘ │
└─────────────────────────────┘
```

The order top-to-bottom: **coach voice first, ripples second**. The coach voice is the high-signal moment; the ripples are the side effect. This is the same order the APNs reply sheet uses today — we're aligning the in-app sheet with the established pattern.

## Wireframe — post-send (failure)

```
┌─────────────────────────────┐
│ Cancel   Log session        │
├─────────────────────────────┤
│ ┌─── form ─ active ───────┐ │  ← form stays editable
│ └─────────────────────────┘ │
│                             │
│ ┌─── tinted rose ─────────┐ │
│ │ ⚠ Couldn't send.        │ │  ← short error
│ │   Try again.            │ │
│ └─────────────────────────┘ │
│                             │
│ [        Send         ]     │  ← re-enabled
└─────────────────────────────┘
```

The sheet **does not dismiss on failure**. The user can:
- Tap Send again
- Edit the friction note before retrying
- Tap Cancel to give up

Failure path in v1 today is `try?` — meaning the call returns nil and the sheet dismisses without telling the user. That's the bug. Fix: catch the error, display it, keep the sheet open.

## Outcome options (unchanged)

Three options on this sheet (vs. five on the APNs reply sheet):

| Outcome | Footer caption | Brain action |
|---|---|---|
| Done | Counts. World grows. | grow + progression check |
| Partial | Holds the load. | log + no add |
| Skipped | Logged. See you tomorrow. | log + slip counter increments |

The footer is **outcome-aware** — it updates as the user changes the picker. Each footer is a static string (not LLM-generated) from the voice spec § 9 footer bank.

## Why three options here vs. five on push

The APNs reply sheet has five outcomes (adds "Not now" and "Busy"). Those two are nudge-specific — they make sense as replies to a coach who just pinged you. They don't make sense as in-app self-reports because the user reaches this sheet by *choosing* to report, not by being interrupted.

If a user opens this sheet but doesn't want to report yet, they tap Cancel. That's the in-app equivalent of "Not now."

## Coach response rendering

The coach response in this sheet is **the same field** as on the APNs reply sheet (`coachResponse` from `POST /actions/{id}/log`). The fact that v1 renders it on one path but not the other is the bug.

The voice transformer at the backend already generates this string in coach voice. No new pipeline work needed for this sheet — just render the field that's already in the response.

If `coachResponse` is empty or missing, hide the "FROM YOUR COACH" card entirely. Don't show "FROM YOUR COACH" with nothing under it, and don't substitute a generic line. Silence beats slop.

## "See what's next" CTA

This is new. After a successful log, the sheet offers a button to jump to the Now tab — which by then shows the *next* prescription (which has just been adapted based on the user's report).

The behavior: tap → sheet dismisses → tab switches to Now → user sees Wednesday's session with the load now showing 155 (the +5 we just earned).

> This is a small detail with a big payoff: it closes the **report → adaptation** loop in a single user-visible motion. The user reports, the coach responds, and the user immediately sees the *consequence* of their report in the prescription. No tracker shows you the consequence in-line. Most adapt invisibly, server-side, and reveal it on the next nudge — by which point the user has forgotten the report.

## States

| State | Trigger | Visual |
|---|---|---|
| Idle | Sheet opened | Form, Send enabled |
| Sending | Send tapped | Send shows spinner, "Sending…", form disabled |
| Sent (success) | Backend returned | Form faded; coach card + ripples shown; "See what's next" + Done buttons |
| Sent (failure) | Network or 5xx | Form stays editable; rose error banner; Send re-enabled |

## Engineering notes

- The backend response for `POST /actions/{id}/log` already includes `coachResponse`, `ripples`, `adaptation`. The iOS side just needs to render `coachResponse` (currently dropped) and add the failure branch.
- The "See what's next" tab switch requires a programmatic tab-selection from a sheet dismiss callback. This is a small SwiftUI plumbing detail — pass the `TabView` selection binding down to the sheet's callback.
- The fade-the-form behavior post-send is a `.disabled(true)` + `.opacity(0.4)` modifier set. Standard.

## Accessibility

- Outcome picker is segmented — VoiceOver should read the current selection and explain that swiping the picker changes outcome.
- The coach response card should be readable as a single accessibility element — VoiceOver says "From your coach: [text]" without separately announcing the eyebrow.
- Ripples are decorative; VoiceOver should read them as a single combined label, not three separate ones.

## Open questions

- Should the coach response include the next-session forecast inline ("Squat goes to 155 Thursday"), or should that live only on the Now tab? Current proposal: inline in the coach response when it's a notable change (≥5 lb progression, exercise swap), omitted when it's a routine hold. The brain decides.
- Should we ask one follow-up if the user picks "Skipped" — like "what got in the way" before sending? Right now the friction field exists but it's optional and on the same screen. Making it a second step after "Skipped" might feel paternalistic. Leaving as-is for v2.
- After a sleep-tracking integration ships, should the coach response reference HealthKit data ("you slept 4h — that explains Thursday")? Probably yes, but post-v2.
