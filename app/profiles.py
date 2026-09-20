"""Profile management service.

Bridges the HTTP layer and persistence: keeps the demo profile read-only and
guarantees stored payloads are valid process parameters.
"""

from __future__ import annotations

from typing import Any

from .config import DEMO_PROFILE_NAME
from .errors import ProfileConflictError, ProfileNotFoundError
from . import persistence
from .validation import validate_profile_name, validate_process_params


def _params_from_model(params: Any) -> dict[str, float]:
    data = params.model_dump()
    payload = {
        "D": float(data["D"]),
        "S0": float(data["s0"]),
        "mumax": float(data["mumax"]),
        "Ks": float(data["ks"]),
        "Y": float(data["y"]),
    }
    validate_process_params(
        D=payload["D"],
        s0=payload["S0"],
        mumax=payload["mumax"],
        ks=payload["Ks"],
        y=payload["Y"],
    )
    return payload


def get(name: str) -> dict[str, Any]:
    name = validate_profile_name(name)
    profile = persistence.get_profile(name)
    if profile is None:
        raise ProfileNotFoundError(name)
    return profile


def list_all() -> list[dict[str, Any]]:
    return persistence.list_profiles()


def register(name: str, params: Any, description: str = "") -> dict[str, Any]:
    """Create a new named profile; rejects an existing/reserved name."""
    name = validate_profile_name(name)
    if name == DEMO_PROFILE_NAME:
        raise ProfileConflictError(
            f"{DEMO_PROFILE_NAME!r} 是内置示范档，保留名称不可覆盖", name=name
        )
    payload = _params_from_model(params)
    return persistence.create_profile(name, payload, description)


def replace(name: str, params: Any, description: str = "") -> dict[str, Any]:
    """Create-or-update semantics (PUT). The demo profile stays immutable."""
    name = validate_profile_name(name)
    if name == DEMO_PROFILE_NAME:
        raise ProfileConflictError(
            f"{DEMO_PROFILE_NAME!r} 是内置示范档，保留名称不可覆盖", name=name
        )
    payload = _params_from_model(params)
    updated = persistence.update_profile(name, payload, description)
    return updated if updated is not None else persistence.create_profile(
        name, payload, description
    )


def delete(name: str) -> None:
    name = validate_profile_name(name)
    if not persistence.delete_profile(name):
        raise ProfileNotFoundError(name)
