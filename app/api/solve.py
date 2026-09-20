"""Steady-state calculation endpoints (solve one point / sweep dilution)."""

from __future__ import annotations

from fastapi import APIRouter

from .. import config
from ..schemas import (
    ScanPoint,
    ScanRequest,
    ScanResponse,
    SolveRequest,
    SteadyStateResponse,
)
from ..solver import steady_state, sweep_dilution_rate

router = APIRouter(prefix="/api/v1", tags=["steady-state"])


def _response(result) -> SteadyStateResponse:
    return SteadyStateResponse(
        D=result.D,
        S=result.S,
        X=result.X,
        mu=result.mu,
        washout=result.washout,
        regime="washout" if result.washout else "steady_biomass",
    )


@router.post("/solve", response_model=SteadyStateResponse)
def solve(request: SolveRequest) -> SteadyStateResponse:
    """Solve one CSTR steady state for a single parameter set."""
    result = steady_state(
        D=request.D,
        s0=request.s0,
        mumax=request.mumax,
        ks=request.ks,
        y=request.y,
    )
    return _response(result)


@router.post("/scan", response_model=ScanResponse)
def scan(request: ScanRequest) -> ScanResponse:
    """Sweep dilution rate ``D_start``..``D_stop`` (step ``D_step``)."""
    results = sweep_dilution_rate(
        d_start=request.d_start,
        d_stop=request.d_stop,
        d_step=request.d_step,
        s0=request.s0,
        mumax=request.mumax,
        ks=request.ks,
        y=request.y,
        max_points=config.MAX_SCAN_POINTS,
    )
    return ScanResponse(
        count=len(results),
        points=[
            ScanPoint(
                D=r.D, S=r.S, X=r.X, mu=r.mu, washout=r.washout
            )
            for r in results
        ],
    )
