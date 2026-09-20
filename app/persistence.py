"""SQLite persistence for named parameter profiles.

A single lightweight SQLite file inside the container stores named operating
cases ("工况档"). Every call opens a short-lived connection (SQLite handles
the pooling itself via WAL mode); nothing about an in-flight calculation is
ever stored here, so concurrent requests cannot share or overwrite each
other's results.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config
from .config import DEMO_PROFILE_NAME

_SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    name        TEXT PRIMARY KEY,
    D           REAL NOT NULL,
    S0          REAL NOT NULL,
    mumax       REAL NOT NULL,
    Ks          REAL NOT NULL,
    Y           REAL NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    source      TEXT NOT NULL DEFAULT 'user'
                    CHECK (source IN ('builtin', 'user')),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""

# Built-in, hand-checkable aerobic demo case.
# mu = mumax * S / (Ks + S), D = mu at steady state:
#   S* = Ks D / (mumax - D) = 10 * 0.2 / (0.5 - 0.2) = 6.666... mg COD/L
#   X* = Y (S0 - S*) = 0.5 * (200 - 6.666...) = 96.666... mg VSS/L
#   D = 0.2 h^-1 << mumax = 0.5 h^-1, so X* is safely positive.
DEMO_PROFILE: dict[str, Any] = {
    "name": DEMO_PROFILE_NAME,
    "D": 0.2,
    "S0": 200.0,
    "mumax": 0.5,
    "Ks": 10.0,
    "Y": 0.5,
    "description": (
        "内置有氧示范工况: D=0.2 h^-1, S0=200 mg/L, mumax=0.5 h^-1, "
        "Ks=10 mg/L, Y=0.5 mg/mg。手算: S*=6.67 mg/L, X*=96.67 mg/L。"
    ),
    "source": "builtin",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or config.DB_PATH
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db(db_path: str | None = None, *, seed_demo: bool = True) -> None:
    """Create the schema and (idempotently) plant the built-in demo profile."""
    with connect(db_path) as conn:
        conn.execute(_SCHEMA)
        if seed_demo:
            row = conn.execute(
                "SELECT name FROM profiles WHERE name = ?",
                (DEMO_PROFILE_NAME,),
            ).fetchone()
            if row is None:
                ts = _now()
                conn.execute(
                    """
                    INSERT INTO profiles
                        (name, D, S0, mumax, Ks, Y, description, source,
                         created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        DEMO_PROFILE["name"],
                        DEMO_PROFILE["D"],
                        DEMO_PROFILE["S0"],
                        DEMO_PROFILE["mumax"],
                        DEMO_PROFILE["Ks"],
                        DEMO_PROFILE["Y"],
                        DEMO_PROFILE["description"],
                        DEMO_PROFILE["source"],
                        ts,
                        ts,
                    ),
                )


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "name": row["name"],
        "params": {
            "D": row["D"],
            "S0": row["S0"],
            "mumax": row["mumax"],
            "Ks": row["Ks"],
            "Y": row["Y"],
        },
        "description": row["description"],
        "source": row["source"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def get_profile(name: str, db_path: str | None = None) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM profiles WHERE name = ?", (name,)
        ).fetchone()
    return _row_to_dict(row) if row is not None else None


def list_profiles(db_path: str | None = None) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM profiles ORDER BY source DESC, name ASC"
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def create_profile(
    name: str,
    params: dict[str, float],
    description: str,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Insert a new profile; returns ``None``-style marker via IntegrityError."""
    ts = _now()
    with connect(db_path) as conn:
        try:
            conn.execute(
                """
                INSERT INTO profiles
                    (name, D, S0, mumax, Ks, Y, description, source,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'user', ?, ?)
                """,
                (
                    name,
                    params["D"],
                    params["S0"],
                    params["mumax"],
                    params["Ks"],
                    params["Y"],
                    description,
                    ts,
                    ts,
                ),
            )
        except sqlite3.IntegrityError as exc:
            from .errors import ProfileConflictError

            raise ProfileConflictError(
                f"工况档名称已存在: {name!r}", name=name
            ) from exc
    found = get_profile(name, db_path)
    assert found is not None
    return found


def update_profile(
    name: str,
    params: dict[str, float],
    description: str,
    db_path: str | None = None,
) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        cur = conn.execute(
            """
            UPDATE profiles
               SET D = ?, S0 = ?, mumax = ?, Ks = ?, Y = ?,
                   description = ?, updated_at = ?
             WHERE name = ?
            """,
            (
                params["D"],
                params["S0"],
                params["mumax"],
                params["Ks"],
                params["Y"],
                description,
                _now(),
                name,
            ),
        )
        if cur.rowcount == 0:
            return None
    return get_profile(name, db_path)


def delete_profile(name: str, db_path: str | None = None) -> bool:
    """Delete a profile. Built-in profiles are protected."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT source FROM profiles WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            return False
        if row["source"] == "builtin":
            from .errors import ProfileConflictError

            raise ProfileConflictError(
                f"内置工况档 {name!r} 受保护，不允许删除", name=name
            )
        conn.execute("DELETE FROM profiles WHERE name = ?", (name,))
    return True
