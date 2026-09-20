"""Steady-state solver for a single CSTR with Monod kinetics.

Mass balances at steady state (no endogenous decay):

    biomass:   D * X = mu(S) * X                 ->  D = mu  (when X > 0)
    substrate: D * (S0 - S) = mu(S) * X / Y

With ``mu = mumax * S / (Ks + S)`` the non-trivial branch gives

    S* = Ks * D / (mumax - D)
    X* = Y * (S0 - S*)

Physical boundaries (enforced here, never by feeding a negative denominator
into the formula):

* ``D >= mumax`` -> washout: ``X = 0``, ``S = S0``. The critical point
  ``D == mumax`` is handled explicitly so the denominator never vanishes.
* ``D < mumax`` but ``S* >= S0`` -> the non-trivial branch would predict
  ``X* <= 0``, i.e. the operating point is also beyond the washout boundary;
  washout is returned just the same.

Inputs are assumed already validated by :mod:`app.validation`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .kinetics import specific_growth_rate
from .validation import (
    grid_steps,
    validate_process_params,
    validate_scan_range,
)


@dataclass(frozen=True)
class SteadyState:
    """A verified steady-state operating point."""

    D: float
    S: float
    X: float
    mu: float
    S0: float
    mumax: float
    Ks: float
    Y: float
    washout: bool


def steady_state(
    *, D: float, s0: float, mumax: float, ks: float, y: float
) -> SteadyState:
    """Return the steady state for one operating condition.

    ``D`` must be strictly positive here; the sweep never visits ``D <= 0``.
    """
    validate_process_params(D=D, mumax=mumax, ks=ks, y=y, s0=s0)

    # Critical washout boundary: D == mumax is handled before any division,
    # and D > mumax is the classic hydraulic washout regime.
    if D >= mumax:
        return SteadyState(
            D=D,
            S=s0,
            X=0.0,
            # Microbes in the influent-free reactor would grow at this rate,
            # but it cannot keep up with the dilution rate.
            mu=specific_growth_rate(s0, mumax, ks),
            S0=s0,
            mumax=mumax,
            Ks=ks,
            Y=y,
            washout=True,
        )

    s_star = ks * D / (mumax - D)

    # Non-trivial solution must predict positive biomass. S* == S0 means
    # zero biomass, which is itself the washout boundary.
    if s_star >= s0:
        return SteadyState(
            D=D,
            S=s0,
            X=0.0,
            mu=specific_growth_rate(s0, mumax, ks),
            S0=s0,
            mumax=mumax,
            Ks=ks,
            Y=y,
            washout=True,
        )

    x_star = y * (s0 - s_star)
    # Guard against a negative result slipping through from rounding; the
    # branch above already guarantees a strictly positive difference.
    if x_star <= 0.0 or not math.isfinite(x_star):
        return SteadyState(
            D=D,
            S=s0,
            X=0.0,
            mu=specific_growth_rate(s0, mumax, ks),
            S0=s0,
            mumax=mumax,
            Ks=ks,
            Y=y,
            washout=True,
        )

    return SteadyState(
        D=D,
        S=s_star,
        X=x_star,
        # On the non-washout branch the steady-state identity is mu == D.
        mu=D,
        S0=s0,
        mumax=mumax,
        Ks=ks,
        Y=y,
        washout=False,
    )


def sweep_dilution_rate(
    *,
    d_start: float,
    d_stop: float,
    d_step: float,
    s0: float,
    mumax: float,
    ks: float,
    y: float,
    max_points: int,
) -> list[SteadyState]:
    """Compute steady states over ``D_start`` .. ``D_stop`` inclusive.

    The grid is ``D_start + k * D_step``; the final point is snapped onto
    ``D_stop`` when the interval length is an integer number of steps (up to
    floating-point tolerance).
    """
    count = validate_scan_range(d_start, d_stop, d_step, max_points)
    # Validate the process parameter set up front so an invalid entry never
    # yields a partial scan; steady_state() re-validates per point as well.
    validate_process_params(D=d_start, mumax=mumax, ks=ks, y=y, s0=s0)

    points: list[SteadyState] = []
    n_steps = count - 1
    _, exact_endpoint = grid_steps(d_start, d_stop, d_step)
    for k in range(count):
        if k == n_steps and exact_endpoint and n_steps > 0:
            dilution = d_stop
        else:
            dilution = d_start + k * d_step
        points.append(
            steady_state(D=dilution, s0=s0, mumax=mumax, ks=ks, y=y)
        )
    return points
