"""Parameter validation.

Physical admissibility rules are kept here (rather than only in Pydantic
field constraints) so that the kinetics/steady-state core can never be driven
with nonsense values even when it is called directly, e.g. from tests or
another Python client.

Rules:
    D     (dilution rate)    > 0
    mumax (max growth rate)  > 0
    ks    (half saturation)  > 0
    y     (yield coefficient)> 0
    s0    (influent substrate) >= 0
"""

from __future__ import annotations

import math

from .errors import InvalidParametersError

# Public parameter names used across the API (see schemas aliases).
S0 = "S0"
D = "D"
MUMAX = "mumax"
KS = "Ks"
Y = "Y"

# Internal-key -> (public name, predicate description)
_PROCESS_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("D", D, "稀释率必须为正数"),
    ("mumax", MUMAX, "最大比增长速率必须为正数"),
    ("ks", KS, "半饱和常数必须为正数"),
    ("y", Y, "产率系数必须为正数"),
    ("s0", S0, "进水基质浓度不可为负"),
)


def _is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def validate_process_params(
    *, D: float, mumax: float, ks: float, y: float, s0: float
) -> None:
    """Raise :class:`InvalidParametersError` listing *every* bad field."""
    values = {"D": D, "mumax": mumax, "ks": ks, "y": y, "s0": s0}
    reasons: dict[str, str] = {}

    for internal, public, rule in _PROCESS_FIELDS:
        value = values[internal]
        if not _is_finite_number(value):
            reasons[public] = "必须是有限实数"
            continue
        if public == S0:
            if float(value) < 0:
                reasons[public] = rule
        else:
            if float(value) <= 0:
                reasons[public] = rule

    if reasons:
        raise InvalidParametersError(reasons)


def grid_steps(d_start: float, d_stop: float, d_step: float) -> tuple[int, bool]:
    """Return ``(n_steps, exact_multiple)`` for the sweep grid.

    ``n_steps`` is the number of steps from start that stay at or before
    stop; ``exact_multiple`` is True when the interval length is an integer
    number of steps (within tolerance), meaning the final grid point sits
    exactly on ``d_stop``. A quotient that is an integer within tolerance is
    treated as exact (absorbing binary float drift); otherwise we take the
    floor, i.e. the grid never extrapolates past ``d_stop``.
    """
    raw = (d_stop - d_start) / d_step
    nearest = round(raw)
    if abs(raw - nearest) <= 1e-9 * max(1, abs(nearest)):
        return max(0, nearest), True
    return max(0, math.floor(raw)), False


def grid_step_count(d_start: float, d_stop: float, d_step: float) -> int:
    """Number of grid steps from start staying at or before stop."""
    return grid_steps(d_start, d_stop, d_step)[0]


def validate_scan_range(
    d_start: float, d_stop: float, d_step: float, max_points: int
) -> int:
    """Validate a dilution-rate sweep interval and return its point count."""
    reasons: dict[str, str] = {}
    for public, value in (
        ("D_start", d_start),
        ("D_stop", d_stop),
        ("D_step", d_step),
    ):
        if not _is_finite_number(value):
            reasons[public] = "必须是有限实数"

    if not reasons:
        if d_start <= 0:
            reasons["D_start"] = "起始稀释率必须为正数"
        if d_step <= 0:
            reasons["D_step"] = "步长必须为正数"
        if d_stop < d_start:
            reasons["D_stop"] = "终止稀释率不可小于起始稀释率"
        if not reasons:
            count = grid_step_count(d_start, d_stop, d_step) + 1
            if count > max_points:
                reasons["D_step"] = (
                    f"扫描点数 {count} 超出上限 {max_points}，请加大步长或缩小区间"
                )

    if reasons:
        raise InvalidParametersError(reasons)

    return count


def validate_profile_name(name: object) -> str:
    """Profiles are named with a non-empty, bounded, printable string."""
    if not isinstance(name, str):
        raise InvalidParametersError({"name": "工况档名称必须是字符串"})
    stripped = name.strip()
    if not stripped:
        raise InvalidParametersError({"name": "工况档名称不能为空"})
    if len(stripped) > 128:
        raise InvalidParametersError({"name": "工况档名称不可超过 128 个字符"})
    if any(ch.isspace() and ch != " " for ch in stripped):
        raise InvalidParametersError({"name": "工况档名称不可包含换行等控制字符"})
    return stripped
