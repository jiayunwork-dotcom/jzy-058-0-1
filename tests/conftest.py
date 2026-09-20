"""Shared test fixtures.

Each test run uses an isolated temporary SQLite file; the demo profile is
seeded fresh. Tests talk to the ASGI app in-process via httpx's
ASGITransport (no real network sockets).
"""

from __future__ import annotations

import os

import pytest

# Point the service at a temp database *before* app modules read config.
os.environ.setdefault("STEADY_DB_PATH", "/tmp/steady_test_default.db")


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    path = str(tmp_path / "test_steady.db")
    monkeypatch.setenv("STEADY_DB_PATH", path)
    # config reads DB_PATH at import time; patch the constants directly too.
    from app import config

    monkeypatch.setattr(config, "DB_PATH", path)
    from app import persistence

    persistence.init_db(path)
    yield path


@pytest.fixture()
def client(db_path):
    from starlette.testclient import TestClient

    from app.main import app

    # TestClient runs the lifespan, which initialises the schema + demo row
    # against the patched db_path.
    with TestClient(app) as c:
        yield c
