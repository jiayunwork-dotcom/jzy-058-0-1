"""Named-profile persistence and HTTP behaviour."""

from __future__ import annotations

import pytest

from app.config import DEMO_PROFILE_NAME


def test_builtin_demo_profile_seeded_and_solves(client):
    r = client.get(f"/api/v1/profiles/{DEMO_PROFILE_NAME}")
    assert r.status_code == 200
    profile = r.json()
    assert profile["source"] == "builtin"
    assert profile["params"]["D"] == 0.2

    solved = client.post(f"/api/v1/profiles/{DEMO_PROFILE_NAME}/solve")
    assert solved.status_code == 200
    body = solved.json()
    assert body["S"] == pytest.approx(6.6666667, rel=1e-7)
    assert body["X"] == pytest.approx(96.6666667, rel=1e-7)
    assert body["washout"] is False


def test_demo_appears_in_listing(client):
    r = client.get("/api/v1/profiles")
    names = [p["name"] for p in r.json()["profiles"]]
    assert DEMO_PROFILE_NAME in names


def test_register_retrieve_update_delete_profile(client):
    payload = {
        "name": "case_a",
        "params": {"D": 0.3, "S0": 500, "mumax": 0.6, "Ks": 20, "Y": 0.4},
        "description": "测试档 A",
    }
    r = client.post("/api/v1/profiles", json=payload)
    assert r.status_code == 201, r.text
    assert r.json()["source"] == "user"

    got = client.get("/api/v1/profiles/case_a")
    assert got.status_code == 200
    assert got.json()["params"]["S0"] == 500

    # PUT replaces
    payload["params"]["D"] = 0.35
    r = client.put("/api/v1/profiles/case_a", json=payload)
    assert r.status_code == 200
    assert r.json()["params"]["D"] == 0.35

    solved = client.post("/api/v1/profiles/case_a/solve")
    assert solved.json()["D"] == 0.35

    r = client.delete("/api/v1/profiles/case_a")
    assert r.status_code == 204
    assert client.get("/api/v1/profiles/case_a").status_code == 404


def test_duplicate_name_rejected(client):
    payload = {
        "name": "dup",
        "params": {"D": 0.3, "S0": 500, "mumax": 0.6, "Ks": 20, "Y": 0.4},
    }
    assert client.post("/api/v1/profiles", json=payload).status_code == 201
    r = client.post("/api/v1/profiles", json=payload)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "profile_conflict"


def test_demo_profile_is_protected(client):
    payload = {
        "name": DEMO_PROFILE_NAME,
        "params": {"D": 0.3, "S0": 500, "mumax": 0.6, "Ks": 20, "Y": 0.4},
    }
    assert client.post("/api/v1/profiles", json=payload).status_code == 409
    assert client.put(f"/api/v1/profiles/{DEMO_PROFILE_NAME}",
                      json=payload).status_code == 409
    assert client.delete(f"/api/v1/profiles/{DEMO_PROFILE_NAME}").status_code == 409
    # Still intact
    assert client.get(f"/api/v1/profiles/{DEMO_PROFILE_NAME}").status_code == 200


def test_get_unknown_profile_404(client):
    r = client.get("/api/v1/profiles/does_not_exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "profile_not_found"


def test_delete_unknown_profile_404(client):
    assert client.delete("/api/v1/profiles/nope").status_code == 404


def test_register_rejects_invalid_params(client):
    payload = {
        "name": "bad",
        "params": {"D": 0, "S0": 500, "mumax": 0.6, "Ks": 20, "Y": 0.4},
    }
    r = client.post("/api/v1/profiles", json=payload)
    assert r.status_code == 422


def test_register_rejects_blank_name(client):
    payload = {
        "name": "   ",
        "params": {"D": 0.3, "S0": 500, "mumax": 0.6, "Ks": 20, "Y": 0.4},
    }
    assert client.post("/api/v1/profiles", json=payload).status_code == 422


def test_profile_persists_across_connections(db_path, client):
    payload = {
        "name": "persisted",
        "params": {"D": 0.25, "S0": 320, "mumax": 0.7, "Ks": 12, "Y": 0.42},
    }
    client.post("/api/v1/profiles", json=payload)
    # A fresh persistence layer view (simulating restart) sees the row.
    from app import persistence

    record = persistence.get_profile("persisted")
    assert record is not None
    assert record["params"]["mumax"] == 0.7


def test_solve_unknown_profile_404(client):
    r = client.post("/api/v1/profiles/ghost/solve")
    assert r.status_code == 404
