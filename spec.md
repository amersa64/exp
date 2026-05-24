# Project Spec: The Coach — An Agentic Behavior-Change Copilot for iOS

> **Document purpose.** This is the authoritative brief for the agent building this app. It contains the vision, the behavioral-science theory it rests on, the full feature set, the architecture, a deliberately narrow v1 scope, an explicit list of anti-patterns to avoid, and — most importantly — a **Fidelity Rubric** (Section 12) the building agent should use to continuously evaluate whether what it's building matches the intent. When in doubt, re-read Section 2 (Principles) and score against Section 12.

---

## 1. The One-Sentence Thesis

**Build a phone-based AI copilot that acts like a world-class personal coach for whatever goal the user is chasing — it assesses you, owns the planning, pushes intelligent nudges at the right moment, executes real work in your calendar, follows up on what it asked you to do, and reflects your real-world progress back as a living, growing world you collect and unlock.**

Everything below is in service of that sentence. If a feature doesn't serve it, cut the feature.

---

## 2. Core Principles (Non-Negotiable)

These are the constitution. Every design decision is checked against them.

1. **Push, not pull.** This is not a dashboard you open, check, and maintain. Its core job is to *initiate*. The intelligence lives in deciding **what** to say and **when**. The cognitive load of planning and remembering moves *off the user and onto the agent*. If the user has to open the app to make it useful, we have failed.

2. **Copilot, not chatbot.** A chatbot is stateless, reactive, and changes nothing in the world. This is an *agent*. It must have all four of these properties or it's just ChatGPT:
   - **Persistence** — it holds a durable model of the user and the goal across sessions; it is never a fresh chat.
   - **Initiative** — it reaches out first (the nudge).
   - **Execution** — it does real work in the world (writes to the calendar, sets reminders).
   - **Loop-closing** — it remembers what it asked the user to do and *follows up* on it. ("You blocked 6pm for a run — did it happen? No? What got in the way, and when should we move it?")

3. **Coach, not assistant.** Generic = slop. The value of the agent is inversely proportional to how generic it is. "Block 30 minutes of workout" offloads nothing — the calendar already does that. A real coach **removes the deciding**: it assesses the person, owns the programming, prescribes the specific session, and *adapts the next one based on what the user reported*. The expertise IS the product.

4. **Assessment before prescription.** The agent's first move on any new goal is NEVER to dump a plan. It is to *interview* — exactly like a coach's first session is mostly questions. Prescription comes only after intake.

5. **Grand in depth before grand in breadth.** A mediocre coach for fifty goals is just slop hidden one layer down. Be *unreasonably excellent at ONE domain first* (fitness for v1), prove the entire loop, then generalize the machinery. Narrow and deep beats wide and shallow.

6. **The world is a mirror, never a game you play.** Growth in the world is earned ONLY by verified real-world behavior — never by tapping in the app. The moment you can level up by engaging with the app itself, it becomes a parallel game the user optimizes *instead of* their life, and the whole thing is worthless. Reality is the input; the world is the reflection.

7. **Nudge quality is the entire product, and restraint is part of quality.** The failure mode is notification blindness. The instant it feels like nagging, it gets muted and dies. A great nudge engine often says *less* than expected, and never the same templated ping twice.

8. **Know the edge of competence.** For anything medical, mental-health, injury, or otherwise high-risk, the coach must recognize the boundary of its expertise and hand off to a human/professional. "Grand" must never become "liability."

---

(See the original brief for Sections 3–13 in full — theory, brain, hierarchy, world, nudges, connectivity, architecture, v1 scope, anti-patterns, **Fidelity Rubric**, and build sequence. They are the contract this codebase is built against; treat them as load-bearing. The README scores this commit against Section 12.)
