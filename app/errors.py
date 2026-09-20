"""Domain and API error types.

All failures raised by the steady-state service are subclasses of
:class:`SteadyStateError` so the FastAPI layer can render them with one
uniform, structured envelope::

    {"error": {"code": "...", "message": "...", "details": {...}}}
"""

from __future__ import annotations

from typing import Any


class SteadyStateError(Exception):
    """Base class for every error understood by the service."""

    code: str = "steady_state_error"
    status_code: int = 400

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.details: dict[str, Any] = details or {}


class InvalidParametersError(SteadyStateError):
    """One or more process / sweep parameters violate physical bounds."""

    code = "invalid_parameters"
    status_code = 422

    def __init__(self, reasons: dict[str, str], message: str | None = None) -> None:
        if message is None:
            message = "工况参数不合法: " + "; ".join(
                f"{field}: {reason}" for field, reason in reasons.items()
            )
        super().__init__(message, details={"reasons": reasons})


class ProfileNotFoundError(SteadyStateError):
    """A named parameter profile does not exist."""

    code = "profile_not_found"
    status_code = 404

    def __init__(self, name: str) -> None:
        super().__init__(f"工况档不存在: {name!r}", details={"name": name})


class ProfileConflictError(SteadyStateError):
    """Profile name collides with a reserved/locked entry."""

    code = "profile_conflict"
    status_code = 409

    def __init__(self, message: str, *, name: str) -> None:
        super().__init__(message, details={"name": name})
