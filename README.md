# The Coach

Backend brain + iOS scaffold for the agentic behavior-change copilot specified in `spec.md` (the brief that started this build).

The north star is Section 1 of the spec. The conscience is Section 2. The scorecard is Section 12. **Re-read those before adding features.**

---

## What's in this repo

```
backend/coach/        the brain — runnable Python, fully tested
  models.py             Section 5 hierarchy + WorldState (mirror principle enforced)
  store.py              SQLite; the second line of defense for mirror integrity
  llm.py                Anthropic SDK wrapper; stub fallback so it runs offline
  safety.py             Section 4.4 hard floor (medical / injury / mental-health)
  nudge.py              Section 7 — timing + variety + restraint + back-off
  lifecycle.py          Section 4.1 master loop: intake → program → prompt →
                        execute → report → adapt → loop-closing
  personas/
    base.py             Persona interface (data-driven by design, Rubric G2)
    fitness.py          The ONE v1 persona — real novice linear progression
  integrations/
    calendar.py         Google Calendar interface + in-memory stub
    healthkit.py        HealthKit interface + in-memory stub
backend/tests/        11 tests, each mapped to a rubric item
cli/demo.py           run the entire coaching lifecycle end-to-end in the terminal
ios/                  SwiftUI scaffold (not yet buildable — see ios/README.md)
spec.md               (paste the original brief here for posterity)
```

## Run it

```bash
pip install -e ".[dev]"
python -m cli.demo          # walks the whole lifecycle, prints what the brain decided
python -m pytest backend    # 11 passing tests
```

Optional, for real LLM output instead of the stub:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python -m cli.demo
```

---

## Self-evaluation against Section 12 (Fidelity Rubric)

Honest scores for **this commit**. Anything below 2 on a load-bearing (★) dimension is called out.

### A. Copilot character (★)
| | |
|---|---|
| A1 Persistence | **3** — SQLite-backed; `test_persistence_across_coach_instances` proves the brain survives process death. |
| A2 Initiative | **2** — `try_nudge` decides when to fire from calendar/health context, not a clock. No real scheduler-cron yet (would be a small loop in production). |
| A3 Execution | **2** — calendar EXECUTE is fully implemented against an interface; real Google Calendar adapter needs OAuth, not wired here. |
| A4 Loop-closing | **3** — `open_followups()` surfaces what the coach asked for that the user didn't answer. Demoed live. |

### B. Coaching depth (★)
| | |
|---|---|
| B1 Assessment-first | **3** — INTAKE runs before PROGRAM, enforced by `RuntimeError` if you skip it. |
| B2 Specificity | **3** — nudges name lifts/sets/reps/load, never "30 min workout". |
| B3 Adaptation | **3** — `test_program_adapts_to_done_report` + `test_program_deloads_after_two_partials` prove the program actually changes from reports. |
| B4 Domain expertise | **2** — novice linear progression is real and conservative; will pass a strength coach. Periodization for intermediates is not built. |
| B5 Safety boundary | **2** — pattern-based handoff exists and is tested. Tune patterns and add LLM-side safety reasoning before shipping. |

### C. Push-not-pull (★)
| | |
|---|---|
| C1 Useful without opening | **2** — backend can run the loop autonomously; iOS app's role is purely to display + reply (no planning UI). |
| C2 Load off the user | **3** — user only ever reports outcomes, never plans. |
| C3 World is read-only | **3** — `WorldState.grow()` is the only mutation path; store rejects writes without a `VerifiedEvent`. |

### D. Nudge quality (★)
| | |
|---|---|
| D1 Contextual timing | **2** — calendar gaps + HealthKit signals drive timing. Real M+A inference deserves more signal; v1 baseline is in. |
| D2 Variety | **2** — LLM-authored with explicit variety prompt + random seed. Stub falls back to 7 rotating voices; with real Sonnet it's actually varied. |
| D3 Restraint | **3** — daily cap + cooldown + back-off after ignored, all tested. Silence is a legitimate output of `decide_timing`. |
| D4 Carries prescription | **3** — body contains the actual session and an implementation intention. |
| D5 One-tap reply loop | **3** — `record_report` ingests outcome + friction, immediately feeds adaptation. |

### E. The world (★ on E3)
| | |
|---|---|
| E1 Fusion | **1** — model supports unlocks + living systems + collection currency; visual treatment is a sketch, not yet "a town". This is Section 13 step 6 work. |
| E2 Hierarchy rendering | **1** — four-zoom scaffold exists in SwiftUI but not built/visually polished. |
| E3 Mirror integrity (★) | **3** — `WorldState.grow()` requires a `VerifiedEvent`; `Store.save_world()` rejects writes whose growth-source doesn't match. Test `test_world_cannot_grow_without_verified_event` is the proof. |
| E4 Upward ripple | **2** — `grow()` returns human-readable ripples ("+7 effort · streak: 1 day · living system thriving"). Visual ripple animation is later. |

### F. Connectivity
| | |
|---|---|
| F1 Calendar read | **1** — interface + stub; real Google Calendar OAuth adapter not built here. |
| F2 Calendar write | **1** — same — `execute_in_calendar` works against the interface. |
| F3 HealthKit | **1** — interface + stub; iOS-side reads scaffolded. |

### G. Scope discipline
| | |
|---|---|
| G1 Depth-first | **3** — exactly one persona (fitness). No second domain. |
| G2 Authorable personas | **3** — `Persona` is a data-class of callables; adding domain #2 is authoring a new file in `personas/`, not editing the engine. |

### H. Vibe check
Honest: without the real Google Calendar + APNs + HealthKit pipes, you can't feel it as a phone copilot yet. But the **brain itself** demonstrably does the right thing — runs the loop, follows up, refuses to grow the world from in-app taps, adapts the program from reports. The hard part (the *logic of being a coach*) is real. The visible-product polish (the world's actual visuals + real iOS app) is the remaining work.

---

## What's NOT in this commit (and why)

| Out | Why |
|---|---|
| Google Calendar OAuth adapter | needs real client credentials + a hosted callback URL; out of scope for a single-session build |
| APNs / push server | needs Apple Developer account + signing key |
| HTTP layer (FastAPI) for the brain | the Python API IS the brain; bolt FastAPI on top — it's a thin port |
| Polished "town" world visuals | Section 13 step 6 — do it last, after the loop is proven |
| Domain #2 | Section 2 Principle 5 (depth before breadth) and Section 10 (v1 scope) |

## Next steps, in spec-suggested order (Section 13)

1. ✅ Data model + backend skeleton (done)
2. ✅ Coaching lifecycle text-only (done, runnable)
3. ☐ iOS client + APNs (scaffold present; needs Xcode build)
4. ◐ Nudge engine (done at logic layer; needs real push delivery)
5. ◐ Calendar + HealthKit (interfaces done; needs real adapters)
6. ☐ Growing world visuals
7. ☐ Re-score this rubric on a real device after two weeks of use
