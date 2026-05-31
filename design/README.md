# The Coach — design files

A flow-first, code-free way to iterate on the iOS app's UX. Each file describes one screen (or one cluster of related screens) using ASCII wireframes + a short role brief + entry/exit transitions + open UX questions.

**The point of this directory:** iterate on the *shape of the experience* — not the visuals, not the code. When the flow is right, the iOS engineering catches up.

## Read in this order

1. [`FLOW.md`](FLOW.md) — the whole app as a navigation graph (mermaid). Start here.
2. `screens/01-connectivity-states.md` — what the user sees before the app is usable.
3. `screens/02-intake.md` — the conversation that bootstraps a user. The single biggest UX risk after install.
4. The world tabs, in their tab-bar order:
   - `03-train-tab.md` — the "what do I do now" surface. Default landing.
   - `04-train-log-session.md` — the report path that closes the loop.
   - `05-summit-tab.md` — identity + the growing mountain.
   - `06-milestones-tab.md` — waypoints toward the summit.
   - `07-habits-tab.md` — living-system vitality.
   - `08-today-tab.md` — what the coach has been saying + what's owed.
5. `09-nudge-reply.md` — the modal that lands from APNs or follow-ups.
6. `10-settings.md` — minimal admin sheet.

## What each screen file contains

```
## Role           one-paragraph "what is this screen for"
## Wireframe      monospaced ASCII layout
## Content states empty / loading / loaded / failed
## Enters from    where the user came from
## Exits to       where the user can go next
## UX questions   open issues to discuss with a designer
```

The wireframes are deliberately ugly. They show **structure and hierarchy** so we can talk about whether the right things are in the right places — not pixel polish.

## Conventions used in the wireframes

```
┌─┐  outer phone frame
│ │  vertical separators
─    horizontal divider
●    selected option / filled element
○    unselected option / empty element
▓░   progress bar (filled / unfilled)
[ ]  primary button
[·]  ghost / secondary button
…    truncated text
{X}  variable / dynamic value
```

## Where the design lives in the spec

The flow is built on top of the spec at `../spec.md`. The relevant sections:
- §1 north star (push-not-pull copilot)
- §4.1 master loop (intake → program → prompt → execute → report → adapt)
- §6 the growing world (4-level zoom: Summit / Milestones / Habits / Today)
- §7 nudge engine (timing, variety, restraint, one-tap reply)

When a screen exists *because of a spec section*, the file cites it.
