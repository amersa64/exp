"""
Vitals — the broad HealthKit ingestion catalog + trend math (pure).

The iOS client reads everything Health will grant and posts batches of
VitalSample; the backend stores them as a rolling per-metric time series so the
coach can reason about TRENDS. This module owns:

  - METRICS: the canonical metric catalog (key → label, unit, direction, tier).
  - trend helpers: slope, window summary, sleep debt — all pure functions over
    lists of (datetime, value), testable without a device or a store.

DESIGN CONSTRAINT (per product): nothing here REQUIRES an Apple Watch. Metrics
are tiered:
  - "core"     : iPhone-native (steps, distance, flights) — essentially always
                 available on a modern iPhone with motion access.
  - "body"     : body composition (weight, body fat, BMI) — from a smart scale
                 or entered by hand; no Watch needed.
  - "sleep"    : time in bed / asleep — iPhone sleep schedule or a sleep app.
  - "optional" : Watch-derived enrichment (resting HR, HRV, VO2max, …). Read if
                 some device happens to write it; never gate a feature on it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class MetricSpec:
    key: str
    label: str
    unit: str
    # "up" = higher is better, "down" = lower is better, "neutral" = context.
    direction: str
    tier: str  # core | body | sleep | optional


# The canonical catalog. The iOS reader maps each HealthKit type to one of
# these keys; the dashboard renders whatever keys actually have data.
METRICS: dict[str, MetricSpec] = {m.key: m for m in [
    # --- iPhone-native (no Watch) ---------------------------------------
    MetricSpec("steps", "Steps", "steps", "up", "core"),
    MetricSpec("distance_km", "Walk + run distance", "km", "up", "core"),
    MetricSpec("flights_climbed", "Flights climbed", "flights", "up", "core"),
    # --- Body composition (smart scale / manual) ------------------------
    MetricSpec("body_mass_kg", "Body weight", "kg", "neutral", "body"),
    MetricSpec("body_fat_pct", "Body fat", "%", "down", "body"),
    MetricSpec("lean_mass_kg", "Lean mass", "kg", "up", "body"),
    MetricSpec("bmi", "BMI", "", "neutral", "body"),
    MetricSpec("height_cm", "Height", "cm", "neutral", "body"),
    # --- Sleep (iPhone sleep schedule / sleep apps) ---------------------
    MetricSpec("sleep_asleep_h", "Sleep", "h", "up", "sleep"),
    MetricSpec("sleep_in_bed_h", "Time in bed", "h", "neutral", "sleep"),
    # --- Optional Watch enrichment (never required) ---------------------
    MetricSpec("resting_hr", "Resting heart rate", "bpm", "down", "optional"),
    MetricSpec("hrv_ms", "HRV (SDNN)", "ms", "up", "optional"),
    MetricSpec("vo2max", "Cardio fitness (VO₂max)", "mL/kg·min", "up", "optional"),
    MetricSpec("respiratory_rate", "Respiratory rate", "br/min", "neutral", "optional"),
    MetricSpec("active_energy_kcal", "Active energy", "kcal", "up", "optional"),
    MetricSpec("exercise_min", "Exercise minutes", "min", "up", "optional"),
]}


def spec_for(metric: str) -> MetricSpec | None:
    return METRICS.get(metric)


# ---------------------------------------------------------------------------
# Trend math — pure functions over [(datetime, value)] pairs, newest-last.
# ---------------------------------------------------------------------------

def linear_slope_per_day(points: list[tuple[datetime, float]]) -> float | None:
    """Least-squares slope in value-units PER DAY. None if <2 distinct days.

    Used for weight trajectory, VO2max trend, etc. We regress value against
    days-since-first so the slope is interpretable as "per day" regardless of
    sampling cadence.
    """
    if len(points) < 2:
        return None
    t0 = points[0][0]
    xs = [(t - t0).total_seconds() / 86400.0 for t, _ in points]
    ys = [v for _, v in points]
    n = len(xs)
    sx, sy = sum(xs), sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys))
    denom = n * sxx - sx * sx
    if denom == 0:
        return None
    return (n * sxy - sx * sy) / denom


def summarize_metric(metric: str, points: list[tuple[datetime, float]]) -> dict | None:
    """A dashboard-ready summary of one metric's recent history.

    Returns current value, sample count, the change across the window, a
    per-week slope, and whether the movement is "good" given the metric's
    direction (so the UI can color it). None for empty input.
    """
    if not points:
        return None
    points = sorted(points, key=lambda p: p[0])
    spec = spec_for(metric)
    current = points[-1][1]
    first = points[0][1]
    change = current - first
    slope_day = linear_slope_per_day(points)
    slope_week = slope_day * 7 if slope_day is not None else None

    direction_good: bool | None = None
    if spec and spec.direction in ("up", "down") and abs(change) > 1e-9:
        improving = change > 0 if spec.direction == "up" else change < 0
        direction_good = improving

    return {
        "metric": metric,
        "label": spec.label if spec else metric,
        "unit": spec.unit if spec else "",
        "tier": spec.tier if spec else "optional",
        "current": round(current, 2),
        "n": len(points),
        "change": round(change, 2),
        "slope_per_week": round(slope_week, 3) if slope_week is not None else None,
        "direction_good": direction_good,
        "first_at": points[0][0].isoformat(),
        "last_at": points[-1][0].isoformat(),
    }


def sleep_debt(points: list[tuple[datetime, float]], target_h: float = 7.5, nights: int = 7) -> float | None:
    """Accumulated sleep deficit over the last `nights` nights, in hours.

    Sums (target - asleep) per night, flooring each night's contribution at 0
    (a great night doesn't "pay back" a bad one in how the body feels). None if
    no sleep data. This is the multi-day signal that makes recovery smarter than
    a single morning — and it's iPhone-friendly (sleep duration, not stages).
    """
    if not points:
        return None
    recent = sorted(points, key=lambda p: p[0])[-nights:]
    debt = sum(max(0.0, target_h - v) for _, v in recent)
    return round(debt, 1)
