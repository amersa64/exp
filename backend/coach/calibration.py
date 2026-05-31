"""
Calibration + benchmark engine.

Two responsibilities:

  1. Estimate a one-rep-max from an observed work set, using the Epley
     formula. This converts a logged "5 reps at 145 lb" into a usable
     1RM number for both program prescription and percentile lookup.

  2. Look up a percentile / label for a given (lift, sex, age, bodyweight,
     1RM) tuple, using a small table of well-known strength-standard
     ratios. These ratios are derived from public reference data
     (Strength Level, ExRx, T-Nation classifications) — they are not
     intended to be clinical-grade, but they are good enough to tell a
     novice from an intermediate lifter, which is what the user actually
     needs to hear.

The full calibration flow lives in the persona — this module is the
deterministic math + reference data. Keeping it pure makes it testable
and lets every persona share the same benchmark logic without each one
hard-coding ratios.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


# --- 1RM estimation ----------------------------------------------------------

def epley_1rm(load_lb: float, reps: int) -> float:
    """
    Epley formula: 1RM ≈ load * (1 + reps/30).

    For a clean single rep, returns the load itself. Becomes less accurate
    above ~10 reps; we cap there to avoid wild estimates from very high-rep
    sets that aren't really strength tests anyway.
    """
    if reps <= 0:
        return 0.0
    if reps == 1:
        return load_lb
    capped = min(reps, 10)
    return round(load_lb * (1 + capped / 30), 1)


# --- Benchmark tables --------------------------------------------------------
#
# Each table maps a lift slot to a list of (label, ratio) pairs, where ratio
# is "estimated 1RM ÷ bodyweight." The first ratio is the cutoff for
# "untrained"; subsequent ratios are the cutoffs for the next labels.
#
# Numbers below are conservative averages of Strength Level (Mar 2024) and
# ExRx's "untrained / novice / intermediate / advanced / elite" thresholds,
# rounded to one decimal. Female ratios are roughly 0.7x male ratios — a
# well-documented average that breaks down at the extremes but is fine for
# our "rough percentile" use case.
#
# We use four canonical labels: untrained, novice, intermediate, advanced.
# Elite is intentionally omitted — anyone who'd be in that bucket is a
# competitive lifter and almost certainly doesn't need this app to tell them
# where they stand. Better to underclaim than overclaim.

LiftSlot = Literal["bench", "squat", "deadlift", "ohp", "row", "pullup"]
Sex = Literal["male", "female"]
Label = Literal["untrained", "novice", "intermediate", "advanced"]

# Ratio thresholds for ADULT MALE (~25-45y, average bodyweight band).
# Format: { lift: [ (label, min_ratio), ... ] in ascending order }.
_MALE_RATIOS: dict[str, list[tuple[Label, float]]] = {
    "bench":    [("untrained", 0.0), ("novice", 0.75), ("intermediate", 1.15), ("advanced", 1.55)],
    "squat":    [("untrained", 0.0), ("novice", 1.00), ("intermediate", 1.50), ("advanced", 2.10)],
    "deadlift": [("untrained", 0.0), ("novice", 1.25), ("intermediate", 1.80), ("advanced", 2.50)],
    "ohp":      [("untrained", 0.0), ("novice", 0.45), ("intermediate", 0.70), ("advanced", 1.00)],
    "row":      [("untrained", 0.0), ("novice", 0.70), ("intermediate", 1.05), ("advanced", 1.40)],
    # Pullup is special — the percentile bands are raw rep counts (not a
    # load/bodyweight ratio, which is always >=1 for bodyweight pullups and
    # therefore useless as a discriminator). benchmark() detects lift=="pullup"
    # and treats the user's logged rep count as the "ratio" for table lookup.
    "pullup":   [("untrained", 0.0), ("novice", 4.0), ("intermediate", 10.0), ("advanced", 18.0)],
}

# Female lifters: rough rule of thumb is ~70% of male ratios for upper body,
# ~80% for lower body. Pulling movements sit in between.
_FEMALE_MULTIPLIERS: dict[str, float] = {
    "bench":    0.65,
    "squat":    0.80,
    "deadlift": 0.80,
    "ohp":      0.65,
    "row":      0.70,
    "pullup":   0.50,
}


# Bodyweight bands change the ratios slightly — heavier lifters can move
# less weight relative to bodyweight (allometric scaling). These multipliers
# adjust the base ratios. Same idea applies in opposite direction for very
# light lifters but our band step is coarse so the correction stays simple.
def _bodyweight_adjustment(bodyweight_lb: float) -> float:
    if bodyweight_lb < 130:    return 1.10   # very light — ratios run hotter
    if bodyweight_lb < 165:    return 1.05
    if bodyweight_lb < 200:    return 1.00   # baseline (the table is set here)
    if bodyweight_lb < 235:    return 0.95
    return 0.90                              # heavy — ratios run cooler


# Age decay: strength standards taper above 40. Modest correction; the
# longevity persona has its own assessment so this only really matters for
# the lifting personas.
def _age_adjustment(age: int) -> float:
    if age < 40:               return 1.00
    if age < 50:               return 0.95
    if age < 60:               return 0.90
    if age < 70:               return 0.82
    return 0.75


# --- Percentile lookup -------------------------------------------------------

@dataclass(frozen=True)
class BenchmarkResult:
    """The full benchmark verdict for one observed lift."""
    lift: str
    est_1rm_lb: float
    ratio: float          # est_1rm / bodyweight
    label: Label
    # Position within the user's label band, 0.0-1.0. Useful for "you're just
    # over the novice line" vs "deep into intermediate" phrasing.
    band_pct: float
    # Approx population percentile, 0.0-1.0. Coarse — derived from label
    # positions. Better than nothing; not clinical.
    percentile: float


def _ratios_for(lift: str, sex: Sex, age: int, bodyweight_lb: float
                ) -> list[tuple[Label, float]]:
    base = _MALE_RATIOS[lift]
    sex_mult = _FEMALE_MULTIPLIERS[lift] if sex == "female" else 1.0
    bw_mult = _bodyweight_adjustment(bodyweight_lb)
    age_mult = _age_adjustment(age)
    mult = sex_mult * bw_mult * age_mult
    return [(label, ratio * mult) for label, ratio in base]


# Mapping label → approximate population percentile floor. Used to assign a
# rough "you're at the 45th percentile" number for the Becoming tab. These
# are anchored to what serious strength communities call out as the share
# of lifters at each level (Starting Strength, /r/Fitness wiki).
_LABEL_FLOOR: dict[Label, float] = {
    "untrained":    0.00,
    "novice":       0.25,
    "intermediate": 0.60,
    "advanced":     0.90,
}
_LABEL_CEIL: dict[Label, float] = {
    "untrained":    0.25,
    "novice":       0.60,
    "intermediate": 0.90,
    "advanced":     0.99,
}


def benchmark(lift: str, sex: Sex, age: int, bodyweight_lb: float,
              reps: int, load_lb: float) -> BenchmarkResult:
    """
    Compute the full benchmark verdict for an observed top set.

    Pullup is special-cased: the "load" should be passed as 0 with reps
    set to the count of clean bodyweight pull-ups. The function will
    convert that into a pseudo-1RM as `bodyweight × (1 + reps/30)`.
    """
    if lift == "pullup":
        # est_1rm is still bodyweight × (1+reps/30) — useful elsewhere — but
        # for the table lookup we use raw rep count, because the pullup
        # table is keyed on reps, not load ratios.
        est_1rm = bodyweight_lb * (1 + min(reps, 10) / 30)
        ratio = float(reps)
    else:
        est_1rm = epley_1rm(load_lb, reps)
        ratio = est_1rm / max(bodyweight_lb, 1.0)

    bands = _ratios_for(lift, sex, age, bodyweight_lb)
    # Walk from highest band down — first one whose floor we've cleared wins.
    label: Label = "untrained"
    label_floor = 0.0
    label_ceil = bands[1][1] if len(bands) > 1 else 1.0
    for i in range(len(bands) - 1, -1, -1):
        name, floor = bands[i]
        if ratio >= floor:
            label = name
            label_floor = floor
            label_ceil = bands[i + 1][1] if i + 1 < len(bands) else floor * 1.5
            break

    band_pct = (ratio - label_floor) / max(label_ceil - label_floor, 0.01)
    band_pct = max(0.0, min(1.0, band_pct))

    # Interpolate inside the label's population percentile range.
    pop_floor = _LABEL_FLOOR[label]
    pop_ceil = _LABEL_CEIL[label]
    percentile = pop_floor + (pop_ceil - pop_floor) * band_pct

    return BenchmarkResult(
        lift=lift,
        est_1rm_lb=round(est_1rm, 1),
        ratio=round(ratio, 2),
        label=label,
        band_pct=round(band_pct, 2),
        percentile=round(percentile, 2),
    )


# --- Weakest lift / emphasis -------------------------------------------------

def weakest_lift(results: dict[str, dict[str, float | int | str]]) -> str | None:
    """
    Given a calibration_results dict, return the slot with the lowest
    percentile — that becomes the program's emphasis for the active phase.

    Ties broken by ratio (lower wins). Returns None if no results yet.
    """
    if not results:
        return None
    ranked = sorted(
        results.items(),
        key=lambda kv: (
            float(kv[1].get("percentile", 1.0)),
            float(kv[1].get("ratio", 99.0)),
        ),
    )
    return ranked[0][0]


# --- Starting load from observed data ---------------------------------------

def starting_load_from_calibration(observed: dict[str, float | int | str],
                                    pct_of_1rm: float = 0.65,
                                    floor_lb: float = 25.0,
                                    rounding_lb: float = 5.0) -> float:
    """
    Convert a single calibration_results entry into a starting working
    load for the active program. Defaults to 65% of estimated 1RM — between
    the strength persona's old 70% (too aggressive when it was off guessed
    1RMs) and the conditioning 55% (too conservative when we actually
    know the user's number).

    Rounds DOWN to the nearest plate increment so the user always starts
    with a load they can hit cleanly. The whole point of calibration is
    to never sandbag the user with a too-heavy start.
    """
    est_1rm = float(observed.get("est_1rm_lb", 0.0))
    if est_1rm <= 0:
        return floor_lb
    raw = est_1rm * pct_of_1rm
    rounded = (int(raw // rounding_lb)) * rounding_lb
    return max(floor_lb, float(rounded))


# --- Shared calibration session builders (lifting personas) ------------------
#
# Strength, hypertrophy, discipline, and (with a different battery) longevity
# all need to assess the user's actual capacity before prescribing the real
# program. The lifting personas share an identical assessment — different
# starting-load policies, but same probes. These builders are reused across
# personas; each persona passes its own slot ladders (which exercises map
# to "squat" / "bench" / etc. given the user's equipment).

from .exercises import catalog, Exercise  # noqa: E402  (avoids circular at top)
from .models import (                       # noqa: E402
    ExercisePrescription, Session, UserProfile,
)


_WARMUP_BLURB = ("Warm up first: 2-3 lighter sets, climbing. Then take 2-3 "
                 "work-up sets to the heaviest 5 you can do with crisp form. "
                 "That last clean set is what you log — reps + load.")


def _probe(slot: str, ladders: dict[str, list[str]],
           equipment: set[str | None], rest: int = 180,
           extra_note: str = "") -> ExercisePrescription:
    """One calibration probe: tagged with calibration_slot so iOS prompts
    for a top-set log. The user discovers the load — we never prescribe
    a number we don't have evidence for."""
    ex: Exercise = catalog().pick_for_slot(ladders[slot], equipment)
    base = "Work UP to a top clean set — don't grind, stop when form breaks. "
    return ExercisePrescription(
        name=ex.name,
        sets=1,
        reps=5,
        load_lb=None,
        rest_seconds=rest,
        notes=(base + (extra_note or ex.first_instruction() or ""))[:200],
        calibration_slot=slot,
    )


def lifting_calibration_days(slot_ladders: dict[str, list[str]],
                              equipment_for_profile: callable
                              ) -> list[callable]:
    """
    Return the canonical 5-session lifting calibration battery as a list
    of (program, profile) -> Session callables.

    Personas use this verbatim. The only thing they vary is which exercise
    fills each slot (via their own _SLOT_LADDERS) and which equipment-set
    extractor they pass.
    """
    def lower(_program, profile: UserProfile) -> Session:
        eq = equipment_for_profile(profile.answers.get("equipment"))
        return Session(
            name="Calibration 1 of 5 — Lower baseline",
            summary="Squat work-up to a top clean set of 5.",
            exercises=[_probe("squat", slot_ladders, eq, rest=180,
                              extra_note=_WARMUP_BLURB)],
            expected_minutes=25,
            progression_rule="Don't push to failure. The number we want is "
                             "your heaviest 5 that still looked like the third "
                             "one. We use it to set your real working load.",
        )

    def upper_push(_program, profile: UserProfile) -> Session:
        eq = equipment_for_profile(profile.answers.get("equipment"))
        return Session(
            name="Calibration 2 of 5 — Upper push baseline",
            summary="Bench top set, then OHP top set.",
            exercises=[
                _probe("bench", slot_ladders, eq, rest=180, extra_note=_WARMUP_BLURB),
                _probe("ohp",   slot_ladders, eq, rest=150,
                       extra_note="Same idea — work up to a clean top 5."),
            ],
            expected_minutes=30,
            progression_rule="Two lifts, same approach. We learn how your "
                             "pushing compares to your pulling.",
        )

    def upper_pull(_program, profile: UserProfile) -> Session:
        eq = equipment_for_profile(profile.answers.get("equipment"))
        pullup_note = ("Max strict pullups in one set. If you can't yet, use a "
                       "band or jump-and-lower — log how many you did. Load = 0 "
                       "for bodyweight.")
        return Session(
            name="Calibration 3 of 5 — Upper pull baseline",
            summary="Row top set, then max strict pullups (or assisted).",
            exercises=[
                _probe("row",    slot_ladders, eq, rest=150, extra_note=_WARMUP_BLURB),
                _probe("pullup", slot_ladders, eq, rest=120, extra_note=pullup_note),
            ],
            expected_minutes=25,
            progression_rule="Pullup count is the cleanest read on relative "
                             "pulling strength. Honest counts only.",
        )

    def hinge(_program, profile: UserProfile) -> Session:
        eq = equipment_for_profile(profile.answers.get("equipment"))
        return Session(
            name="Calibration 4 of 5 — Hinge baseline",
            summary="Deadlift work-up to a top clean set of 5.",
            exercises=[_probe("deadlift", slot_ladders, eq, rest=240,
                              extra_note=_WARMUP_BLURB +
                              " Form first — if the back rounds, that set didn't count.")],
            expected_minutes=30,
            progression_rule="Deadlift calibration ends on a clean set, not a "
                             "hero set. If you have any doubt about the next "
                             "jump, that's your top.",
        )

    def conditioning(_program, _profile: UserProfile) -> Session:
        # Conditioning baseline — Cooper test, gentle. No calibration_slot;
        # the user logs distance in the friction note.
        return Session(
            name="Calibration 5 of 5 — Conditioning baseline",
            summary="12-minute walk/run — measure distance covered.",
            exercises=[
                ExercisePrescription(
                    name="12-minute walk/run",
                    sets=1, reps=1, load_lb=None, rest_seconds=0,
                    notes="Cooper test, gentle version. Go as far as you can "
                          "in 12 minutes — walk, jog, or run; you choose. Log "
                          "the distance in the friction note (e.g. '1.4 miles, "
                          "mostly jog').",
                    duration_min=12,
                ),
            ],
            expected_minutes=15,
            progression_rule="This is the cardio floor. We re-test in 6 weeks "
                             "to see how the strength work has carried over.",
        )

    return [lower, upper_push, upper_pull, hinge, conditioning]


# --- Longevity calibration battery (functional assessment) -------------------
#
# Longevity users don't have a "5RM bench" — that's not their world, and
# benchmarking against the strength ratios would feel both wrong (older
# adults have legitimately different ratios) and unhelpful (the goal isn't
# being intermediate at squat, it's still doing your own laundry at 85).
#
# Instead the calibration probes functional capacity:
#   - sit-to-stand (lower body strength + endurance, captured as reps)
#   - wall pushup count (upper body capacity)
#   - single-leg stand seconds (balance — strongest fall-risk predictor)
#   - farmer's-walk carry (grip + posture under load)
#   - 6-minute walk distance (aerobic floor)
#
# The "calibration_slot" tags are unique to longevity (sit_stand_reps,
# wall_pushup, balance_seconds, etc.) so the standard strength benchmark
# table doesn't fire for them — record_top_sets handles "no benchmark"
# gracefully (we still store the raw observation).


def _longevity_probe(name: str, slot: str, instructions: str,
                     load_lb_hint: str = "0 for bodyweight",
                     rest_seconds: int = 60) -> ExercisePrescription:
    return ExercisePrescription(
        name=name,
        sets=1,
        reps=1,
        load_lb=None,
        rest_seconds=rest_seconds,
        notes=f"{instructions} Log your number; {load_lb_hint}.",
        calibration_slot=slot,
    )


def longevity_calibration_days() -> list[callable]:
    """
    Five functional assessments for the longevity persona. Each session is
    one or two short probes — way less than a strength calibration, because
    the population is more fragile and over-testing here costs more than it
    yields. We're learning whether your sit-to-stand is 5 reps or 30 reps —
    not whether you can squat 1.5x bodyweight.
    """
    def session_lower(_program, _profile: UserProfile) -> Session:
        return Session(
            name="Calibration 1 of 5 — Sit-to-stand",
            summary="As many sit-to-stands as you can in 60 seconds.",
            exercises=[
                _longevity_probe(
                    name="Sit-to-stand (60 sec)",
                    slot="sit_stand_reps",
                    instructions=(
                        "Sit in a sturdy chair, arms across chest. Stand up, "
                        "sit back down, repeat for 60 seconds — count clean "
                        "reps. Stop early if anything pinches or you can't "
                        "keep the form. The number is the number."
                    ),
                    load_lb_hint="leave lb blank — bodyweight",
                ),
            ],
            expected_minutes=10,
            progression_rule="No grinding. Honest count beats a hero one.",
        )

    def session_push(_program, _profile: UserProfile) -> Session:
        return Session(
            name="Calibration 2 of 5 — Push count",
            summary="Max clean wall pushups (or floor if you can).",
            exercises=[
                _longevity_probe(
                    name="Wall pushup (or floor pushup)",
                    slot="wall_pushup",
                    instructions=(
                        "Hands on a sturdy wall at chest height — feet a "
                        "step back. Push slowly, ear-to-wall and back. "
                        "Count clean reps until form breaks. If wall is "
                        "easy and you've done pushups before, do floor "
                        "pushups instead — note in friction which one."
                    ),
                    load_lb_hint="leave lb blank — bodyweight",
                ),
            ],
            expected_minutes=10,
            progression_rule="Stop when the second-to-last rep was the last "
                             "clean one. We don't need failure to learn this.",
        )

    def session_balance(_program, _profile: UserProfile) -> Session:
        return Session(
            name="Calibration 3 of 5 — Balance",
            summary="How long can you stand on one leg, eyes open?",
            exercises=[
                _longevity_probe(
                    name="Single-leg stand (eyes open)",
                    slot="balance_seconds",
                    instructions=(
                        "Stand near a wall in case. Lift one foot a few "
                        "inches off the ground. Time how long until you "
                        "lose balance OR have to touch down. Do it on each "
                        "side, log the worse side. Eyes open this time — "
                        "we may test eyes-closed later."
                    ),
                    load_lb_hint="enter seconds in 'reps', leave lb blank",
                ),
            ],
            expected_minutes=10,
            progression_rule="Balance is the single strongest predictor of "
                             "fall-free aging. This number matters.",
        )

    def session_carry(_program, _profile: UserProfile) -> Session:
        return Session(
            name="Calibration 4 of 5 — Carry",
            summary="Heaviest pair of grocery bags you can carry 30 steps.",
            exercises=[
                _longevity_probe(
                    name="Farmer's carry — work-up",
                    slot="carry_lb",
                    instructions=(
                        "Pick up a weight in each hand — dumbbells, kettle "
                        "bells, water jugs, whatever. Walk 30 steps standing "
                        "tall. If easy, add weight, try again. Log the "
                        "heaviest pair you carried with crisp posture, in "
                        "lb per hand."
                    ),
                    load_lb_hint="lb is per-hand",
                ),
            ],
            expected_minutes=15,
            progression_rule="Carry capacity is grocery capacity is grand"
                             "kid capacity is suitcase capacity. Real-life "
                             "strength.",
        )

    def session_walk(_program, _profile: UserProfile) -> Session:
        return Session(
            name="Calibration 5 of 5 — Walk pace",
            summary="6-minute walk — how far do you go?",
            exercises=[
                ExercisePrescription(
                    name="6-minute walk",
                    sets=1, reps=1, load_lb=None, rest_seconds=0,
                    notes=("Walk at a comfortable-but-purposeful pace for "
                           "6 minutes — outside or on a treadmill. Log the "
                           "distance in the friction note (e.g. '0.4 miles' "
                           "or '700 m'). This is the cardio floor we work "
                           "from."),
                    duration_min=6,
                ),
            ],
            expected_minutes=10,
            progression_rule="The 6-minute walk is the gold standard "
                             "cardio screen for older adults. Honest pace "
                             "today, not race pace.",
        )

    return [session_lower, session_push, session_balance,
            session_carry, session_walk]


# --- Shared adaptation helper -----------------------------------------------

def record_top_sets(program, profile: UserProfile,
                    top_sets: dict[str, dict[str, float]]) -> list[str]:
    """
    Persist top sets from a calibration log into program.calibration_results,
    converting each into an estimated 1RM + percentile via the benchmark
    engine. Returns a list of short human-readable summaries (for the
    rationale string the coach narrates back to the user).

    Reads sex / age / bodyweight from the profile. Missing values fall back
    to median-male defaults — partial data still benchmarks, just with less
    accuracy. The persona's own _benchmark_user_factors helper builds the
    (sex, age, bw) tuple — we expose it here too for personas that want it.
    """
    if not top_sets:
        return []
    sex, age, bw = benchmark_user_factors(profile)
    summaries: list[str] = []
    for slot, payload in top_sets.items():
        try:
            reps = int(payload.get("reps", 0))
            load = float(payload.get("load_lb", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
        if reps <= 0:
            continue
        # Some personas (longevity) probe slots that aren't in the strength
        # benchmark table — sit_stand_reps, balance_seconds, carry_lb, etc.
        # For those we still persist the raw observation; we just can't
        # produce a percentile against the population.
        if slot in _MALE_RATIOS:
            verdict = benchmark(slot, sex, age, bw, reps, load)
            program.calibration_results[slot] = {
                "reps": reps,
                "load_lb": load,
                "est_1rm_lb": verdict.est_1rm_lb,
                "ratio": verdict.ratio,
                "percentile": verdict.percentile,
                "label": verdict.label,
            }
            load_str = f"{int(load)} lb × {reps}" if load > 0 else f"{reps} reps BW"
            summaries.append(f"{slot} {load_str} → {verdict.label} "
                             f"(~{int(verdict.percentile * 100)}th pct)")
        else:
            # Functional probe — no benchmark, just the number.
            program.calibration_results[slot] = {
                "reps": reps,
                "load_lb": load,
                "est_1rm_lb": 0.0,
                "ratio": 0.0,
                "percentile": 0.0,
                "label": "observed",
            }
            unit_hint = "sec" if slot.endswith("_seconds") else (
                "lb" if load > 0 else "reps"
            )
            value = int(load) if (unit_hint == "lb" and load > 0) else reps
            summaries.append(f"{slot} {value} {unit_hint}")
    return summaries


def benchmark_user_factors(profile: UserProfile) -> tuple[str, int, float]:
    """Pull (sex, age, bodyweight_lb) from the profile with safe defaults.
    Used by record_top_sets and any persona that wants to benchmark on its
    own."""
    derived = profile.derived
    answers = profile.answers
    sex_raw = str(derived.get("sex") or answers.get("sex") or "male").lower().strip()
    sex = "female" if sex_raw.startswith("f") else "male"
    age_raw = derived.get("age") or answers.get("age") or 30
    try:
        age = int(str(age_raw).split()[0])
    except (ValueError, IndexError):
        age = 30
    bw_raw = (derived.get("bodyweight_lb") or answers.get("bodyweight_lb")
              or derived.get("bodyweight") or 180)
    try:
        bw = float(str(bw_raw).split()[0])
    except (ValueError, IndexError):
        bw = 180.0
    return sex, age, bw
