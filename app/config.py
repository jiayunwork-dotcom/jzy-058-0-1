"""Runtime configuration.

Everything is environment-overridable but the defaults work out of the box
inside the container, where the working directory is ``/app``.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_DB_PATH = str(Path(__file__).resolve().parent.parent / "data" / "steady.db")

DB_PATH: str = os.environ.get("STEADY_DB_PATH", DEFAULT_DB_PATH)
# Upper bound on points a single sweep request may produce (DoS guard).
MAX_SCAN_POINTS: int = int(os.environ.get("STEADY_MAX_SCAN_POINTS", "100000"))

# Name reserved for the built-in, hand-checkable demonstration profile.
DEMO_PROFILE_NAME = "demo_aerobic"
