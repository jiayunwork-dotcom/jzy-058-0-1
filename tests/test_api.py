"""End-to-end HTTP tests through the FastAPI ASGI app."""

from __future__ import annotations

import pytest


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# --------------------------------------------------------------------------
# /solve
# --------------------------------------------------------------------------

def test_solve_happy_path(client):
    r = client.post(
        "/api/v1/solve",
        json={"D": 0.2, "S0": 200, "mumax": 0.5, "Ks": 10, "Y": 0.5},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["S"] == pytest.approx(6.6666667, rel=1e-6)
    assert body["X"] == pytest.approx(96.6666667, rel=1e-6)
    assert body["mu"] == pytest.approx(0.2)
    assert body["washout"] is False
    assert body["regime"] == "steady_biomass"


def test_solve_washout_above_mumax(client):
    r = client.post(
        "/api/v1/solve",
        json={"D": 0.8, "S0": 200, "mumax": 0.5, "Ks": 10, "Y": 0.5},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["washout"] is True
    assert body["regime"] == "washout"
    assert body["X"] == 0.0
    assert body["S"] == 200.0


def test_solve_critical_d_equals_mumax(client):
    r = client.post(
        "/api/v1/solve",
        json={"D": 0.5, "S0": 200, "mumax": 0.5, "Ks": 10, "Y": 0.5},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["washout"] is True
    assert body["X"] == 0.0 and body["S"] == 200.0


def test_solve_s_star_at_or_above_s0_is_washout(client):
    # S* = 10*0.4/0.1 = 40 == S0 -> washout boundary
    r = client.post(
        "/api/v1/solve",
        json={"D": 0.4, "S0": 40, "mumax": 0.5, "Ks": 10, "Y": 0.5},
    )
    body = r.json()
    assert body["washout"] is True and body["X"] == 0.0 and body["S"] == 40.0


def test_solve_rejects_invalid_d(client):
    r = client.post(
        "/api/v1/solve",
        json={"D": -0.1, "S0": 200, "mumax": 0.5, "Ks": 10, "Y": 0.5},
    )
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "invalid_parameters"
    assert "D" in err["details"]["reasons"]


def test_solve_rejects_non_positive_parameters(client):
    base = {"D": 0.2, "S0": 200, "mumax": 0.5, "Ks": 10, "Y": 0.5}
    for field, bad in (("D", 0), ("mumax", -1), ("Ks", 0), ("Y", -0.2)):
        payload = {**base, field: bad}
        r = client.post("/api/v1/solve", json=payload)
        assert r.status_code == 422
        assert field in r.json()["error"]["details"]["reasons"]


def test_solve_rejects_negative_s0(client):
    r = client.post(
        "/api/v1/solve",
        json={"D": 0.2, "S0": -1, "mumax": 0.5, "Ks": 10, "Y": 0.5},
    )
    assert r.status_code == 422
    assert "S0" in r.json()["error"]["details"]["reasons"]


def test_solve_rejects_missing_field(client):
    r = client.post("/api/v1/solve", json={"D": 0.2, "S0": 200})
    assert r.status_code == 422
    reasons = r.json()["error"]["details"]["reasons"]
    assert "mumax" in reasons and "Ks" in reasons and "Y" in reasons


def test_solve_rejects_extra_field(client):
    r = client.post(
        "/api/v1/solve",
        json={"D": 0.2, "S0": 200, "mumax": 0.5, "Ks": 10, "Y": 0.5,
              "decay": 0.01},
    )
    assert r.status_code == 422
    assert "decay" in r.json()["error"]["details"]["reasons"]


def test_solve_rejects_nan_bool_and_string(client):
    base = {"D": 0.2, "S0": 200, "mumax": 0.5, "Ks": 10, "Y": 0.5}
    r = client.post("/api/v1/solve", json={**base, "D": "NaN"})
    assert r.status_code == 422
    r = client.post("/api/v1/solve", json={**base, "D": True})
    assert r.status_code == 422
    r = client.post("/api/v1/solve", json={**base, "Y": "fast"})
    assert r.status_code == 422


# --------------------------------------------------------------------------
# /scan
# --------------------------------------------------------------------------

def test_scan_crossing_mumax(client):
    r = client.post(
        "/api/v1/scan",
        json={
            "D_start": 0.1, "D_stop": 0.6, "D_step": 0.1,
            "S0": 10000, "mumax": 0.5, "Ks": 10, "Y": 0.5,
        },
    )
    assert r.status_code == 200, r.text
    points = r.json()["points"]
    assert r.json()["count"] == 6
    ds = [p["D"] for p in points]
    assert ds == pytest.approx([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    # X positive and strictly decreasing before the boundary...
    assert all(p["X"] > 0 for p in points[:4])
    xs = [p["X"] for p in points[:4]]
    assert all(a > b for a, b in zip(xs, xs[1:]))
    # ...S strictly increasing...
    ss = [p["S"] for p in points[:4]]
    assert all(a < b for a, b in zip(ss, ss[1:]))
    # ...exactly zero at and after D == mumax.
    assert points[4]["X"] == 0.0 and points[4]["washout"] is True
    assert points[5]["X"] == 0.0 and points[5]["washout"] is True
    assert points[5]["S"] == 10000.0


def test_scan_inclusive_stop_with_partial_last_step(client):
    r = client.post(
        "/api/v1/scan",
        json={
            "D_start": 0.1, "D_stop": 0.35, "D_step": 0.1,
            "S0": 10000, "mumax": 0.5, "Ks": 10, "Y": 0.5,
        },
    )
    points = r.json()["points"]
    assert len(points) == 3
    assert points[-1]["D"] == pytest.approx(0.3)  # no extrapolation past stop


def test_scan_rejects_bad_range(client):
    r = client.post(
        "/api/v1/scan",
        json={
            "D_start": 0.5, "D_stop": 0.1, "D_step": 0.1,
            "S0": 100, "mumax": 0.5, "Ks": 10, "Y": 0.5,
        },
    )
    assert r.status_code == 422


def test_scan_rejects_huge_scan(client, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "MAX_SCAN_POINTS", 1000)
    r = client.post(
        "/api/v1/scan",
        json={
            "D_start": 0.0001, "D_stop": 100, "D_step": 0.00001,
            "S0": 100, "mumax": 0.5, "Ks": 10, "Y": 0.5,
        },
    )
    assert r.status_code == 422
    assert "D_step" in r.json()["error"]["details"]["reasons"]
