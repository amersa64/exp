"""Vitals trend math (pure) + broad-ingestion API + multi-day recovery."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from coach import vitals


def _pt(days_ago: float, value: float):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago), value)


# ---- pure trend math -------------------------------------------------------

def test_slope_detects_downward_weight():
    pts = [_pt(28, 82.0), _pt(14, 81.0), _pt(0, 80.0)]
    slope = vitals.linear_slope_per_day(pts)
    assert slope is not None and slope < 0  # losing weight


def test_summarize_marks_direction_good():
    # Body fat going down is "good" (direction=down).
    pts = [_pt(30, 22.0), _pt(0, 19.0)]
    s = vitals.summarize_metric("body_fat_pct", pts)
    assert s["direction_good"] is True
    assert s["current"] == 19.0
    assert s["change"] == -3.0


def test_summarize_unknown_metric_is_neutral():
    s = vitals.summarize_metric("steps", [_pt(1, 8000), _pt(0, 9000)])
    assert s["direction_good"] is True   # steps up is good


def test_sleep_debt_accumulates_short_nights():
    # 7 nights of 6h against a 7.5h target → 1.5h debt each = 10.5h.
    pts = [_pt(i, 6.0) for i in range(7, 0, -1)]
    debt = vitals.sleep_debt(pts, target_h=7.5, nights=7)
    assert debt == pytest.approx(10.5, abs=0.1)


def test_sleep_debt_floors_good_nights_at_zero():
    pts = [_pt(2, 9.0), _pt(1, 5.5)]   # one long, one short
    debt = vitals.sleep_debt(pts, target_h=7.5)
    assert debt == pytest.approx(2.0, abs=0.1)  # only the short night counts


# ---- API + multi-day recovery ---------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DB", str(tmp_path / "coach.db"))
    if "api.app" in sys.modules:
        del sys.modules["api.app"]
    from api.app import app
    with TestClient(app) as c:
        yield c


def _onboard(client, user="vit"):
    headers = {"X-User-Id": user}
    client.post("/intake/submit", json={
        "answers": {"experience": "novice", "days_per_week": "3", "injuries": "none"},
        "identity_statement": "strong + steady",
    }, headers=headers)
    return headers


def test_vitals_ingest_and_summary(client):
    headers = _onboard(client)
    now = datetime.now(timezone.utc)
    samples = []
    for i in range(4):
        at = (now - timedelta(days=21 - i * 7)).isoformat()
        samples.append({"metric": "body_mass_kg", "value": 82.0 - i, "unit": "kg", "at": at})
    samples.append({"metric": "steps", "value": 9000, "unit": "steps"})
    samples.append({"metric": "not_a_metric", "value": 1})  # dropped
    r = client.post("/signals/vitals", json={"samples": samples}, headers=headers)
    assert r.status_code == 200
    assert r.json()["stored"] == 5   # the bogus metric is dropped

    summary = client.get("/vitals/summary", headers=headers).json()
    metrics = {m["metric"]: m for m in summary["metrics"]}
    assert "body_mass_kg" in metrics
    assert metrics["body_mass_kg"]["change"] == -3.0  # 82 → 79
    # Weight trajectory insight present and pointing down.
    kinds = {i["kind"] for i in summary["insights"]}
    assert "weight_trajectory" in kinds


def test_vitals_series_endpoint(client):
    headers = _onboard(client)
    client.post("/signals/vitals", json={"samples": [
        {"metric": "body_mass_kg", "value": 80.0, "unit": "kg"},
    ]}, headers=headers)
    r = client.get("/vitals/series", params={"metric": "body_mass_kg"}, headers=headers)
    assert r.status_code == 200
    assert len(r.json()["points"]) == 1


def test_sleep_debt_drags_readiness_band_down(client):
    headers = _onboard(client)
    now = datetime.now(timezone.utc)
    # A week of 5h nights → heavy debt.
    samples = [
        {"metric": "sleep_asleep_h", "value": 5.0, "unit": "h",
         "at": (now - timedelta(days=i)).isoformat()}
        for i in range(1, 8)
    ]
    client.post("/signals/vitals", json={"samples": samples}, headers=headers)

    # 6.5h this morning scores "ready" on its own…
    r = client.post("/signals/readiness", json={"sleep_hours": 6.5}, headers=headers)
    body = r.json()
    # …but a week of 5h nights drags it down a band and names the debt.
    assert body["band"] in ("easy", "rest")
    assert "sleep debt" in (body["note"] or "")
