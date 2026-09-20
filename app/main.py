"""FastAPI application entry point.

Wires together the HTTP routers, the structured error envelope and the
startup database initialisation. Run with::

    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import contextlib
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import persistence
from .api import profiles as profiles_router
from .api import solve as solve_router
from .errors import SteadyStateError


def _envelope(code: str, message: str, details: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            }
        },
    )


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(SteadyStateError)
    async def _domain_error(_: Request, exc: SteadyStateError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Collapse Pydantic's error list into a field -> Chinese reason map so
        # clients get the same structured shape for invalid inputs regardless
        # of which layer rejected them.
        reasons: dict[str, str] = {}
        for err in exc.errors():
            loc = [str(p) for p in err.get("loc", []) if p != "body"]
            field = _external_name(loc[-1] if loc else "payload")
            reasons[field] = _human_reason(err)
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "invalid_parameters",
                    "message": "工况参数不合法: "
                    + "; ".join(f"{f}: {r}" for f, r in reasons.items()),
                    "details": {"reasons": reasons},
                }
            },
        )


def _external_name(internal: str) -> str:
    return {
        "s0": "S0",
        "D": "D",
        "mumax": "mumax",
        "ks": "Ks",
        "y": "Y",
        "d_start": "D_start",
        "d_stop": "D_stop",
        "d_step": "D_step",
        "name": "name",
        "params": "params",
        "description": "description",
    }.get(internal, internal)


def _human_reason(err: dict) -> str:
    etype = err.get("type", "")
    if etype.endswith("greater_than") or etype == "value_error.number.not_gt":
        return "必须为正数"
    if etype.endswith("greater_than_equal"):
        return "不可为负"
    if etype == "value_error":
        return str(err.get("msg", "取值不合法")).removeprefix("Value error, ")
    if etype in ("missing", "model_type"):
        return str(err.get("msg", "字段缺失或类型错误"))
    if etype in ("extra_forbidden",):
        return "存在不被接受的多余字段"
    return str(err.get("msg", "取值不合法"))


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Schema creation + built-in demo seeding, idempotent on every start.
    persistence.init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="活性污泥 CSTR 稳态求解服务",
        version="1.0.0",
        description=(
            "单级完全混合反应器(CSTR) Monod 动力学稳态核算后端: "
            "单点求解、稀释率区间扫描、冲刷(washout)判定与具名工况档管理。"
        ),
        lifespan=lifespan,
    )
    _register_exception_handlers(app)
    app.include_router(solve_router.router)
    app.include_router(profiles_router.router)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
