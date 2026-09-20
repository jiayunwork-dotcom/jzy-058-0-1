"""Pydantic request/response models.

External field names follow the process-engineering notation of the brief
(``S0``, ``D``, ``mumax``, ``Ks``, ``Y``) while Python code uses snake_case
internally. Extra/unknown fields are rejected so a mistyped parameter can
never silently be ignored.
"""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _strict_float(value: Any) -> float:
    """Reject booleans (lax mode coerces ``True`` -> 1.0) before coercion."""
    if isinstance(value, bool):
        raise ValueError("必须是有限实数，不能是布尔值")
    return value


class ProcessParams(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    s0: float = Field(..., alias="S0", description="进水基质浓度", ge=0)
    mumax: float = Field(..., alias="mumax", description="最大比增长速率", gt=0)
    ks: float = Field(..., alias="Ks", description="半饱和常数", gt=0)
    y: float = Field(..., alias="Y", description="产率系数", gt=0)

    @field_validator("s0", "mumax", "ks", "y", mode="before")
    @classmethod
    def _no_bool(cls, v: Any) -> Any:
        return _strict_float(v)

    @model_validator(mode="after")
    def _reject_non_finite(self) -> "ProcessParams":
        for internal in ("s0", "mumax", "ks", "y"):
            if not math.isfinite(getattr(self, internal)):
                public = {"s0": "S0", "mumax": "mumax", "ks": "Ks", "y": "Y"}[
                    internal
                ]
                raise ValueError(f"{public} 必须是有限实数")
        return self


class SolveRequest(ProcessParams):
    D: float = Field(..., alias="D", description="稀释率", gt=0)

    @field_validator("D", mode="before")
    @classmethod
    def _d_no_bool(cls, v: Any) -> Any:
        return _strict_float(v)

    @model_validator(mode="after")
    def _d_is_finite(self) -> "SolveRequest":
        if not math.isfinite(self.D):
            raise ValueError("D 必须是有限实数")
        return self


class SteadyStateResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    D: float = Field(..., description="稀释率")
    S: float = Field(..., description="稳态出水基质浓度")
    X: float = Field(..., description="稳态污泥(微生物)浓度")
    mu: float = Field(..., description="该基质浓度下的比增长速率")
    washout: bool = Field(..., description="是否处于冲刷状态")
    regime: Literal["washout", "steady_biomass"] = Field(
        ..., description="工况区段: 冲刷 / 有正污泥稳态"
    )


class ScanRequest(ProcessParams):
    d_start: float = Field(..., alias="D_start", description="稀释率区间起点", gt=0)
    d_stop: float = Field(..., alias="D_stop", description="稀释率区间终点(含)", gt=0)
    d_step: float = Field(..., alias="D_step", description="稀释率步长", gt=0)

    @field_validator("d_start", "d_stop", "d_step", mode="before")
    @classmethod
    def _range_no_bool(cls, v: Any) -> Any:
        return _strict_float(v)

    @model_validator(mode="after")
    def _range_is_finite(self) -> "ScanRequest":
        for internal, public in (
            ("d_start", "D_start"),
            ("d_stop", "D_stop"),
            ("d_step", "D_step"),
        ):
            if not math.isfinite(getattr(self, internal)):
                raise ValueError(f"{public} 必须是有限实数")
        if self.d_stop < self.d_start:
            raise ValueError("D_stop 不可小于 D_start")
        return self


class ScanPoint(BaseModel):
    D: float
    S: float
    X: float
    mu: float
    washout: bool


class ScanResponse(BaseModel):
    count: int
    points: list[ScanPoint]


class ProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str = Field(..., description="工况档名称(具名登记)", min_length=1, max_length=128)
    params: SolveRequest
    description: str = Field("", description="备注说明")


class ProfileOut(BaseModel):
    name: str
    params: SolveRequest
    description: str
    source: Literal["builtin", "user"]
    created_at: str
    updated_at: str


class ProfileSummary(BaseModel):
    name: str
    description: str
    source: Literal["builtin", "user"]


class ProfileListResponse(BaseModel):
    profiles: list[ProfileSummary]
