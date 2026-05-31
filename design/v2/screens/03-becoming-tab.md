# 03 — Becoming tab

Identity + Milestones + Habits folded into one scrollable tab. Replaces three v1 tabs with one mental model: *who you're becoming.*

## Role

The Becoming tab is the **history of evidence**. Atomic Habits Ch.2: every action is a vote for the type of person you wish to become. The votes have accumulated. This tab is where the user reviews them. It is the reflective surface, where Now is the active one and Coach is the conversational one.

Three concerns, three scroll sections, one tab:

1. **Identity** (top) — the statement, the votes, the mountain.
2. **Milestones** (middle) — the waypoints. What you've hit, what's next.
3. **Habits** (bottom) — the living systems. What's alive, what's wilting.

The user scrolls top-to-bottom from widest to narrowest zoom (Atomic Habits-meets-spec-§6.1).

## Wireframe — top section: Identity

```
┌─────────────────────────────┐
│ ⚙        Becoming      ●27 │
├─────────────────────────────┤
│                             │
│ FROM YOUR COACH             │  ← restated, in coach voice
│                             │
│ You said you want to be     │  ← identity rendered as
│ someone who shows up,       │     coach-addressed, not
│ even when tired.            │     a museum plaque
│                             │
│ ┌─────────────────────────┐ │
│ │  🏷                       │ │
│ │  27                      │ │  ← BIG number, votes
│ │  votes cast              │ │
│ │  for who you're          │ │
│ │  becoming                │ │
│ └─────────────────────────┘ │
│                             │
│ ┌────────── hero ─────────┐ │
│ │ (the mountain visual)    │ │  ← preserved from v1 Summit
│ │ snow line driven by      │ │     just renamed in code:
│ │ votes count, not currency│ │     growth = votes/50
│ │ aurora driven by         │ │     aura = weeks_active/12
│ │ weeks active             │ │
│ └─────────────────────────┘ │
│                             │
│  8 weeks  · 27 votes  ·     │  ← stat strip
│  longest run: 12 days       │
│                             │
│ ─────────────────────────── │  ← section divider
```

### Key changes from v1 Summit

- **Identity statement** is now framed as coach speech: *"You said you want to be someone who…"*. In v1 it was displayed as a self-quote with the eyebrow "WHO YOU'RE BECOMING." Subtle but important — moving the speaker from the user to the coach shifts the relationship from solitary self-reminder to dialogue.
- **Votes card** is the dominant element (was a secondary card in v1). The number is big, the context line tight. This is the **single most important number in the app**.
- **No streak counter.** Was the third stat in v1. Gone.
- **Stat strip** at the bottom of the section shows three small facts: weeks active, votes, longest unbroken run. "Longest run" replaces "current streak" — historical achievement that can't be invalidated.
- **Mountain hero** is preserved. The shape is still right. Only the data inputs change.

## Wireframe — middle section: Milestones

```
│                             │
│ MILESTONES                  │
│                             │
│ ┌─────────────────────────┐ │
│ │ ●  Squat 5×5 @ body wt   │ │  ← achieved (filled ember)
│ │     Hit Tuesday          │ │     small date
│ │                          │ │
│ │ "Took 6 weeks. Solid."   │ │  ← coach's note, italic
│ └─────────────────────────┘ │     (LLM-generated on
│                             │      first achievement,
│ ┌─────────────────────────┐ │      then frozen)
│ │ ○ 🚩 Squat 5×5 @ 1.25×   │ │  ← next pending
│ │     bodyweight           │ │
│ │     About 4 weeks out    │ │  ← coach's forecast
│ └─────────────────────────┘ │
│                             │
│ ┌─────────────────────────┐ │
│ │ ○ 🚩 Eight unbroken weeks│ │
│ │     Counts rest weeks.   │ │
│ │     6 of 8 so far.       │ │
│ └─────────────────────────┘ │
│                             │
│ ┌─────────────────────────┐ │
│ │ ○ 🚩 …                   │ │  ← collapsed if many
│ │ + 4 more  ›              │ │     pending. tap expands.
│ └─────────────────────────┘ │
│                             │
│ ─────────────────────────── │
```

### Key changes from v1 Milestones tab

- **Tappable rows.** Each opens a detail sheet:
  ```
  Milestone: Squat 5×5 @ 1.25× bodyweight
  
  Target load: 200 lb
  Current best: 150 lb at 5 reps
  
  FROM YOUR COACH
  Steady pace. 4-5 weeks at +5/session
  puts you here. If knee acts up,
  longer.
  ```
- **Coach's note on each row.** Achieved milestones get a one-line LLM-generated reflection at first view (then cached — it doesn't re-generate every time). Pending milestones get a forecast: *"about 4 weeks out."*
- **Achievement is celebrated.** When a milestone is hit, on next app open the Coach tab shows a one-time line: *"Squat 5×5 at bodyweight — done. Took 6 weeks. Solid."* The Becoming tab's milestone row gets a brief ember pulse. No fireworks, no confetti, no "you did it!!!" modal. Marcus-level celebration: a sentence and a moment of light.
- **Limit visible rows.** Show 4 expanded, collapse the rest. Many users will accumulate 15+ milestones over months; the list shouldn't bury what's relevant now.

## Wireframe — bottom section: Habits

```
│                             │
│ LIVING SYSTEMS              │
│                             │
│ ┌─────────────────────────┐ │
│ │  ╭───╮                   │ │
│ │  │ 🍃│  Strength training │ │  ← coach's plain read,
│ │  │84%│  Thriving.         │ │     not just a label
│ │  ╰───╯  Don't change      │ │
│ │         anything.         │ │
│ └─────────────────────────┘ │
│                             │
│ ─────────────────────────── │
│                             │
│ THIS WEEK                   │  ← optional bottom strip
│                             │
│ Sun ─ Mon ▓ Tue ▓ Wed ─     │  ← weekly grid
│ Thu ▓ Fri ─ Sat ─           │     ▓ = trained that day
│                             │     ─ = rest
│ 3 sessions. Most yet.       │     summary line
│                             │
└─────────────────────────────┘
```

### Key changes from v1 Habits tab

- **Coach voice on each habit card.** Was just "Thriving · 84%" in v1; now: *"Strength training. Thriving. Don't change anything."* — Marcus's read on what to do about it. The vitality % is still there but secondary.
- **Tappable.** Detail sheet shows vitality trend (sparkline), days since last verified event, and the coach's interpretation:
  > FROM YOUR COACH
  > 
  > Three sessions a week for the last month. That's why this is alive. Drop below two and it starts to wilt.
- **This week strip** at the bottom. A tiny 7-day grid showing trained / rested days, with a one-line coach summary. This is the *only* place in the app that shows a recent-window grid — historically a tracker UI element, but here scoped tightly: only this week, only as the bottom of the deepest scroll, with a coach summary that contextualizes it. No grid for "this month", "this year", "all time." We are not a tracker.

## Toolbar

Same as the other tabs: gear (settings) on left, votes badge on right.

The votes badge on the Becoming tab is *tappable* to scroll-to-top (jumps to the Identity section with the big votes card). Quality-of-life detail.

## Pull-to-refresh

Refreshes the whole world state: votes count, milestone status, habit vitality, this-week grid. One pull, all three sections refresh. Standard iOS gesture.

## Empty states (per section)

- **Identity:** never empty — the statement is set during intake.
- **Milestones:** *"Milestones load when your program builds."* with the flag icon.
- **Habits:** *"Train once and this fills in."*
- **This-week strip:** if zero sessions this week — *"Quiet week."* No bar visualization, just the text.

## Why this is one tab instead of three

Three reasons:

1. **The user thinks about "who I'm becoming" as one concept, not three.** Tabs implied "three different things to check." A scroll implies "the same thing at different zooms."
2. **A user with one living system and 3 milestones doesn't justify two tabs.** v1's Habits tab in particular felt empty.
3. **Reducing tabs reduces the dashboard fingerprint.** Three tabs say "this app has things to read." Five tabs say "this is a control panel."

## Risks

- **Long scroll.** This tab is the only long-scroll surface in the app. Users may not realize the lower sections exist. Mitigation: section headers are sticky as you scroll, so the user always knows what section they're in. Plus the votes-badge tap-to-top gesture as a known iOS convention.
- **Coach lines on every card may be too much.** If every milestone row and every habit card has a coach-voice quote, the tab starts to feel like a chat history. Mitigation: keep coach-voice lines short (≤12 words per card), and consider rendering only on the *most-relevant* card per section (next pending milestone; currently-deteriorating habit) rather than every card.
- **Mountain visual driving off votes-not-currency** — the calibration may need tuning. 50 votes = full snow line might be too easy or too hard. Plan to recalibrate after 2 weeks of real data.

## Open questions

- Should the "This week" strip move *up* to the Identity section, since it's the most actionable signal? Argument for: people care most about right-now. Argument against: it's the narrowest zoom and belongs at the bottom of the funnel. **Probably leave at bottom; let the Coach tab handle right-now signal.**
- Should achieved milestones be archived after some time (e.g. 90 days), to keep the list short? Probably yes — a year-deep list of achievements would feel like a CV. But that's a v2.1 problem.
- Should we add an "Edit identity" button? Decided no for v2 — identity is set-and-revere. If users push for it, add an explicit "evolve your summit" ritual rather than a free edit.
