"""
Recovery + place math — pure, deterministic, testable without a device.

This is the brain-side of the three iPhone-signal features (Section 8.1).
Everything here is a pure function over numbers so the scoring rule and the
geofence-learning rule can be unit-tested in Python; the iOS client only reads
sensors and posts the raw values. Nothing here touches the store or the LLM.

  - score_readiness()        HealthKit sleep/HR/HRV → 0..100 readiness + band
  - band_directive()         band → how the coach should dial today's ask
  - haversine_m()            distance between two lat/lon points, meters
  - update_place_centroid()  fold a new observation into the learned gym place
"""

from __future__ import annotations

import math

from .models import ReadinessSnapshot, TrainingPlace

# ---------------------------------------------------------------------------
# Readiness scoring.
#
# Three components, each scored 0..1 against the user's own normal where we
# have a baseline, then weighted and summed to 0..100. If a signal is missing
# we drop its weight and renormalize the rest — a user who never grants HRV
# still gets a sensible score from sleep + resting HR alone.
#
# The weights and breakpoints are deliberately conservative: this nudges the
# ask up or down, it does not diagnose. A bad number shrinks the session
# (2-minute rule), it never invents an injury.
# ---------------------------------------------------------------------------

_W_SLEEP = 0.45
_W_RHR = 0.30
_W_HRV = 0.25

# Sleep: full credit at 7.5h, zero at 3h, linear between.
_SLEEP_FULL_H = 7.5
_SLEEP_ZERO_H = 3.0

# Resting HR: at/below baseline = full credit; +12 bpm over baseline = zero.
_RHR_PENALTY_SPAN = 12.0
# HRV: at/above baseline = full credit; 45% below baseline = zero.
_HRV_DROP_SPAN = 0.45

# Fallback population anchors when the client hasn't sent a personal baseline
# yet (first morning, before 14 days of history accrue on-device).
_RHR_DEFAULT_BASELINE = 60.0
_HRV_DEFAULT_BASELINE = 55.0


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _sleep_component(sleep_hours: float) -> float:
    if sleep_hours >= _SLEEP_FULL_H:
        return 1.0
    if sleep_hours <= _SLEEP_ZERO_H:
        return 0.0
    return (sleep_hours - _SLEEP_ZERO_H) / (_SLEEP_FULL_H - _SLEEP_ZERO_H)


def _rhr_component(resting_hr: float, baseline: float) -> float:
    # Lower is better. Below baseline is still full credit (well-rested).
    over = resting_hr - baseline
    if over <= 0:
        return 1.0
    return _clamp01(1.0 - over / _RHR_PENALTY_SPAN)


def _hrv_component(hrv_ms: float, baseline: float) -> float:
    # Higher is better. At/above baseline is full credit.
    if baseline <= 0:
        return 0.5
    drop = (baseline - hrv_ms) / baseline
    if drop <= 0:
        return 1.0
    return _clamp01(1.0 - drop / _HRV_DROP_SPAN)


def score_readiness(snap: ReadinessSnapshot) -> tuple[int, str]:
    """Return (score 0..100, band) for a readiness snapshot.

    Bands: rest (<40), easy (<60), ready (<80), primed (>=80). 'unknown' only
    when no usable signal at all — the coach then proceeds as if 'ready' but
    says nothing about recovery.
    """
    parts: list[tuple[float, float]] = []  # (weight, component 0..1)

    if snap.sleep_hours is not None:
        parts.append((_W_SLEEP, _sleep_component(snap.sleep_hours)))
    if snap.resting_hr is not None:
        baseline = snap.resting_hr_baseline or _RHR_DEFAULT_BASELINE
        parts.append((_W_RHR, _rhr_component(snap.resting_hr, baseline)))
    if snap.hrv_ms is not None:
        baseline = snap.hrv_baseline or _HRV_DEFAULT_BASELINE
        parts.append((_W_HRV, _hrv_component(snap.hrv_ms, baseline)))

    if not parts:
        return 0, "unknown"

    total_w = sum(w for w, _ in parts)
    score01 = sum(w * c for w, c in parts) / total_w
    score = round(score01 * 100)
    return score, readiness_band(score)


def readiness_band(score: int) -> str:
    if score < 40:
        return "rest"
    if score < 60:
        return "easy"
    if score < 80:
        return "ready"
    return "primed"


def multiday_penalty(sleep_debt_h: float | None) -> int:
    """Points to subtract from a single-morning readiness score for accumulated
    sleep debt over the past week.

    A few hours of debt is normal life; we only start docking past ~3h, and cap
    the hit at 20 points so one variable never dominates. This is what makes
    recovery a multi-day read instead of a one-night snapshot — and it leans on
    sleep DURATION (iPhone-friendly), not HRV (Watch-only).
    """
    if not sleep_debt_h or sleep_debt_h <= 3.0:
        return 0
    over = sleep_debt_h - 3.0
    return min(20, round(over * 3))


def band_directive(band: str) -> str:
    """How the coach should shape today's ask given the band.

    Returns one of:
      - "rest"    : recommend the minimum dose / recovery; do not push load.
      - "reduced" : trim volume, hold load — back off without skipping.
      - "full"    : green light, prescribe the planned session.
    """
    if band == "rest":
        return "rest"
    if band == "easy":
        return "reduced"
    # ready / primed / unknown → proceed as planned.
    return "full"


# ---------------------------------------------------------------------------
# Training-place learning.
#
# We never ask the user "where's your gym?" — we learn it. Every time a session
# is started or logged the client posts its current coordinates; we fold them
# into a running centroid. Confidence grows as observations cluster, and the
# fence only goes live once we've seen the spot at least twice (restraint).
# ---------------------------------------------------------------------------

_EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two WGS84 points, in meters."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2)
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


# Two observations more than this far apart are treated as different places —
# the user trained somewhere new (travel, moved gyms). We don't average across
# them; the new cluster takes over and confidence resets.
_NEW_PLACE_THRESHOLD_M = 400.0


def update_place_centroid(
    place: TrainingPlace | None,
    *,
    user_id: str,
    lat: float,
    lon: float,
    label: str = "your gym",
) -> TrainingPlace:
    """Fold one coordinate observation into the learned place.

    First observation seeds the place at confidence 0 (one sample isn't a
    pattern). Subsequent nearby observations move the centroid by 1/n and grow
    confidence. An observation far from the current centroid resets the place
    to the new location — the user trains somewhere else now.
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

    if place is None:
        return TrainingPlace(
            user_id=user_id, lat=lat, lon=lon, label=label,
            samples=1, confidence=0.0, updated_at=now,
        )

    dist = haversine_m(place.lat, place.lon, lat, lon)
    if dist > _NEW_PLACE_THRESHOLD_M:
        # New cluster — start over here rather than dragging the centroid
        # halfway across town.
        return TrainingPlace(
            user_id=user_id, lat=lat, lon=lon, label=label,
            samples=1, confidence=0.0, updated_at=now,
        )

    n = place.samples + 1
    # Running mean: move the centroid 1/n of the way toward the new point.
    new_lat = place.lat + (lat - place.lat) / n
    new_lon = place.lon + (lon - place.lon) / n
    # Confidence saturates toward 1 as samples accumulate; 4 consistent
    # visits ≈ 0.75, which clears the monitorable threshold comfortably.
    confidence = min(1.0, n / 5.0)
    return TrainingPlace(
        user_id=user_id, lat=new_lat, lon=new_lon, label=place.label or label,
        radius_m=place.radius_m, samples=n, confidence=confidence, updated_at=now,
    )
