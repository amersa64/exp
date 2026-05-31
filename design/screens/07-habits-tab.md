# 07 — Habits tab

The living-systems view. Each habit is a plant: it thrives while you feed it, wilts when you don't.

## Role

Zoom 3 of the four-level zoom (spec §6.1). Habits is the *systems* layer — the things that grow because you sustained them. Vitality is a 0→1 scalar derived server-side from consistency over a trailing window. **Thriving** > **Steady** > **Wilting** > **Dormant**.

This is the screen where decay is visible. Miss a week and the leaf darkens. It's a deliberate pressure surface, but a soft one — the brain doesn't shame, the visual just *shows*.

## Wireframe — ready state (one or more living systems)

```
┌─────────────────────────────┐
│ ⚙        Habits         ●23 │
├─────────────────────────────┤
│                             │
│ ┌─────────────────────────┐ │
│ │  ╭───╮                   │ │  ← vitality ring (72×72)
│ │  │ 🍃 │  Strength training│ │     ring fill = vitality
│ │  ╰───╯  Thriving          │ │     color: emerald (>0.7),
│ │   (84%) 84% vitality      │ │             amber (0.4–0.7),
│ │                          │ │             ember (>0),
│ └─────────────────────────┘ │     muted (0)
│                             │
│ A living system thrives     │  ← caption
│ while you sustain it.       │
│                             │
├─────────────────────────────┤
│ 🏋 ⛰ 🚩 🌿 ☀                │
└─────────────────────────────┘
```

## Wireframe — multiple habits (future)

When persona #2 ships, or when the fitness persona starts tracking secondary systems (mobility, sleep), the tab can list more:

```
│ ┌─────────────────────────┐ │
│ │ 🍃  Strength training    │ │
│ │     Thriving · 84%       │ │
│ └─────────────────────────┘ │
│ ┌─────────────────────────┐ │
│ │ 🍃  Sleep window         │ │
│ │     Steady · 56%         │ │
│ └─────────────────────────┘ │
│ ┌─────────────────────────┐ │
│ │ 🍃  Mobility flow        │ │
│ │     Wilting · 22%        │ │
│ └─────────────────────────┘ │
```

## Wireframe — empty state

```
┌─────────────────────────────┐
│ ⚙        Habits         ●0  │
├─────────────────────────────┤
│                             │
│            🍃                │
│                             │
│  Habits aren't growing yet  │
│                             │
│  A living system thrives    │
│  once you start reporting   │
│  verified sessions.         │
│                             │
└─────────────────────────────┘
```

## Vitality bands

| Vitality | Label | Color | What it means |
|---|---|---|---|
| > 0.7 | Thriving | Emerald | Consistent recent activity |
| 0.4 – 0.7 | Steady | Amber | Holding the line |
| > 0.0 | Wilting | Ember | Has lapsed; days since last verified event growing |
| 0.0 | Dormant | Muted gray | Not active or fully decayed |

## Content states

| State | Trigger | Visual |
|---|---|---|
| Ready (filled) | `world.livingSystems` non-empty | habit cards |
| Empty | `world.livingSystems` empty or nil | leaf icon + empty card |
| Loading (world) | Initial fetch of `/world` | this tab silently shows last known or empty |

> The Habits tab does NOT distinguish loading from empty today — both render as the empty card. That's a quiet bug.

## Enters from

- Tab bar → tap Habits
- Pull-to-refresh

## Exits to

- Tab bar → any other tab
- Gear → Settings
- (Habit cards are not tappable today.)

## UX questions

- **A single habit looks lonely.** v1 has one persona (fitness) → one living system. The Habits tab is mostly empty real estate. Worth either deferring this tab until there are 2+ systems, OR making the single-habit view a *richer detail view* (weekly grid, last sessions, decay forecast)?
- **No drill-in.** A user who sees "Wilting · 22%" can't see *why* — what would push it back to Steady? "Train Wednesday and Saturday this week and you're back at Steady" is the kind of guidance this tab is begging for.
- **The pressure feels punitive in isolation.** Decay-based UI works when balanced with the upside — but this tab only shows the current state, not the recent climb. A weekly sparkline would soften "Wilting" into "was Thriving last week, slipped — here's the path back."
- **Conflicts with Milestones.** Habits and Milestones are both "between Summit and Today". A user might wonder why they're separate tabs. Could they fold into a single "Progress" tab with two segmented sub-sections?
- **No habit creation by the user.** The user cannot say "I also want to track meditation" — habits are persona-derived. Is that the right discipline (spec §G1 depth before breadth), or does the v1 fitness coach feel claustrophobic without optional user-authored systems?
- **The leaf metaphor is opinionated.** A user who associates plants with "another thing I forgot to water" might recoil. Worth A/B'ing against a more neutral metaphor (fire, streak chain, sapling-to-tree).
