"""Concurrency isolation tests.

In-flight calculations must never bleed into each other, and many concurrent
profile operations must each land on their own named record.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.config import DEMO_PROFILE_NAME


@pytest.fixture()
async def async_client(db_path):
    from app.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


async def test_concurrent_solves_do_not_cross_contaminate(async_client):
    # Two very different parameter sets fired concurrently and repeatedly.
    payload_a = {"D": 0.1, "S0": 10000, "mumax": 0.5, "Ks": 10, "Y": 0.5}
    payload_b = {"D": 0.45, "S0": 50, "mumax": 0.8, "Ks": 5, "Y": 0.3}

    async def solve(payload):
        r = await async_client.post("/api/v1/solve", json=payload)
        assert r.status_code == 200
        return r.json()

    results = await asyncio.gather(*[solve(payload_a)] * 20 +
                                   [solve(payload_b)] * 20)
    a_results = results[:20]
    b_results = results[20:]

    s_a = 10 * 0.1 / (0.5 - 0.1)
    s_b = 5 * 0.45 / (0.8 - 0.45)
    for body in a_results:
        assert body["S"] == pytest.approx(s_a)
        assert body["washout"] is False
        assert body["X"] == pytest.approx(0.5 * (10000 - s_a))
    for body in b_results:
        assert body["S"] == pytest.approx(s_b)
        assert body["X"] == pytest.approx(0.3 * (50 - s_b))


async def test_concurrent_scans_independent(async_client):
    async def scan(start, stop):
        r = await async_client.post(
            "/api/v1/scan",
            json={
                "D_start": start, "D_stop": stop, "D_step": 0.05,
                "S0": 10000, "mumax": 0.5, "Ks": 10, "Y": 0.5,
            },
        )
        assert r.status_code == 200
        return r.json()

    narrow, wide = await asyncio.gather(scan(0.1, 0.2), scan(0.1, 0.45))
    assert narrow["count"] == 3
    assert wide["count"] == 8


async def test_concurrent_profile_creation_isolated(async_client):
    async def register(i):
        payload = {
            "name": f"parallel_case_{i}",
            "params": {
                "D": 0.1 + i * 0.001,
                "S0": 100 + i,
                "mumax": 0.6,
                "Ks": 10,
                "Y": 0.5,
            },
        }
        r = await async_client.post("/api/v1/profiles", json=payload)
        return r.status_code

    codes = await asyncio.gather(*[register(i) for i in range(20)])
    assert codes == [201] * 20

    listing = await async_client.get("/api/v1/profiles")
    names = {p["name"] for p in listing.json()["profiles"]}
    for i in range(20):
        assert f"parallel_case_{i}" in names


async def test_concurrent_same_name_registration_single_winner(async_client):
    # A race on one name: exactly one 201, every loser gets 409, and the
    # stored record is never partially/corruptly overwritten.
    payload = {
        "name": "race_name",
        "params": {"D": 0.3, "S0": 500, "mumax": 0.6, "Ks": 20, "Y": 0.4},
    }
    codes = await asyncio.gather(*[
        async_client.post("/api/v1/profiles", json=payload) for _ in range(10)
    ])
    statuses = sorted(c.status_code for c in codes)
    assert statuses.count(201) == 1
    assert statuses.count(409) == 9

    got = await async_client.get("/api/v1/profiles/race_name")
    assert got.status_code == 200
    assert got.json()["params"]["D"] == 0.3


async def test_demo_readonly_under_concurrent_load(async_client):
    async def touch_demo():
        r = await async_client.post(f"/api/v1/profiles/{DEMO_PROFILE_NAME}/solve")
        assert r.status_code == 200
        body = r.json()
        assert body["S"] == pytest.approx(6.6666667, rel=1e-7)
        assert body["X"] == pytest.approx(96.6666667, rel=1e-7)

    await asyncio.gather(*[touch_demo() for _ in range(20)])
