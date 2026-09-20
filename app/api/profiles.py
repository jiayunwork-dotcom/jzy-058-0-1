"""Named parameter profile endpoints (register / retrieve / list / delete)."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response

from .. import profiles
from ..schemas import (
    ProfileIn,
    ProfileListResponse,
    ProfileOut,
    ProfileSummary,
    SolveRequest,
    SteadyStateResponse,
)
from ..solver import steady_state

router = APIRouter(prefix="/api/v1/profiles", tags=["profiles"])


def _to_out(record: dict) -> ProfileOut:
    return ProfileOut(
        name=record["name"],
        params=SolveRequest(**record["params"]),
        description=record["description"],
        source=record["source"],
        created_at=record["created_at"],
        updated_at=record["updated_at"],
    )


@router.get("", response_model=ProfileListResponse)
def list_profiles() -> ProfileListResponse:
    records = profiles.list_all()
    return ProfileListResponse(
        profiles=[
            ProfileSummary(
                name=r["name"], description=r["description"], source=r["source"]
            )
            for r in records
        ]
    )


@router.post("", response_model=ProfileOut, status_code=201)
def create_profile(payload: ProfileIn) -> ProfileOut:
    record = profiles.register(
        payload.name, payload.params, payload.description
    )
    return _to_out(record)


@router.put("/{name}", response_model=ProfileOut)
def upsert_profile(name: str, payload: ProfileIn) -> ProfileOut:
    record = profiles.replace(name, payload.params, payload.description)
    return _to_out(record)


@router.get("/{name}", response_model=ProfileOut)
def get_profile(name: str) -> ProfileOut:
    return _to_out(profiles.get(name))


@router.post("/{name}/solve", response_model=SteadyStateResponse)
def solve_profile(name: str) -> SteadyStateResponse:
    """Solve the steady state using a previously stored parameter set."""
    record = profiles.get(name)
    p = record["params"]
    result = steady_state(
        D=p["D"], s0=p["S0"], mumax=p["mumax"], ks=p["Ks"], y=p["Y"]
    )
    return SteadyStateResponse(
        D=result.D,
        S=result.S,
        X=result.X,
        mu=result.mu,
        washout=result.washout,
        regime="washout" if result.washout else "steady_biomass",
    )


@router.delete("/{name}", status_code=204, response_class=Response)
def delete_profile(name: str) -> Response:
    profiles.delete(name)
    return Response(status_code=204)
