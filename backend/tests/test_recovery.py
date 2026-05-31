"""Unit tests for the pure recovery + place math (coach/recovery.py)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from coach import recovery
from coach.models import ReadinessSnapshot, TrainingPlace


def _snap(**kw) -> ReadinessSnapshot:
    return ReadinessSnapshot(user_id="u", **kw)


# ---- readiness scoring -----------------------------------------------------

def test_no_signals_is_unknown():
    score, band = recovery.score_readiness(_snap())
    assert score == 0
    assert band == "unknown"


def test_great_recovery_is_primed():
    score, band = recovery.score_readiness(_snap(
        sleep_hours=8.2, resting_hr=52, hrv_ms=70,
        resting_hr_baseline=55, hrv_baseline=60,
    ))
    assert score >= 80
    assert band == "primed"


def test_wrecked_recovery_is_rest():
    score, band = recovery.score_readiness(_snap(
        sleep_hours=3.5, resting_hr=70, hrv_ms=30,
        resting_hr_baseline=55, hrv_baseline=60,
    ))
    assert score < 40
    assert band == "rest"


def test_sleep_alone_still_scores():
    # A user who only granted sleep still gets a usable band.
    score, band = recovery.score_readiness(_snap(sleep_hours=7.5))
    assert score == 100
    assert band == "primed"

    low, low_band = recovery.score_readiness(_snap(sleep_hours=3.0))
    assert low == 0
    assert low_band == "rest"


def test_resting_hr_below_baseline_is_full_credit():
    # Resting HR under your normal shouldn't be penalized.
    score, _ = recovery.score_readiness(_snap(
        resting_hr=48, resting_hr_baseline=55,
    ))
    assert score == 100


def test_band_directives():
    assert recovery.band_directive("rest") == "rest"
    assert recovery.band_directive("easy") == "reduced"
    assert recovery.band_directive("ready") == "full"
    assert recovery.band_directive("primed") == "full"
    assert recovery.band_directive("unknown") == "full"


# ---- geofence learning -----------------------------------------------------

def test_haversine_known_distance():
    # ~111 km per degree of latitude near the equator.
    d = recovery.haversine_m(0.0, 0.0, 1.0, 0.0)
    assert 110_000 < d < 112_000


def test_first_observation_seeds_low_confidence():
    place = recovery.update_place_centroid(
        None, user_id="u", lat=37.7749, lon=-122.4194,
    )
    assert place.samples == 1
    assert place.confidence == 0.0
    assert not place.monitorable  # one visit isn't a pattern


def test_repeated_nearby_visits_become_monitorable():
    place = None
    # Five visits clustered within a few meters of the same spot.
    for i in range(5):
        place = recovery.update_place_centroid(
            place, user_id="u",
            lat=37.7749 + i * 1e-5, lon=-122.4194 + i * 1e-5,
        )
    assert place.samples == 5
    assert place.confidence >= 0.5
    assert place.monitorable
    # Centroid stays in the cluster.
    assert abs(place.lat - 37.7749) < 0.01


def test_far_observation_resets_to_new_place():
    place = recovery.update_place_centroid(
        None, user_id="u", lat=37.7749, lon=-122.4194,
    )
    place = recovery.update_place_centroid(
        place, user_id="u", lat=37.7750, lon=-122.4195,
    )
    assert place.samples == 2
    # Now train 5km away — a different gym / travel. Centroid jumps, count resets.
    moved = recovery.update_place_centroid(
        place, user_id="u", lat=37.8200, lon=-122.4194,
    )
    assert moved.samples == 1
    assert moved.confidence == 0.0
    assert abs(moved.lat - 37.82) < 0.001
