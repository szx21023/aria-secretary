"""統一錯誤 envelope handlers — 同一個 trace_id 串起 client 回應與 server log，
client 拿到的 traceId 一定 grep 得回完整 traceback。

所有錯誤回應統一成：
    {"error": {"code", "message", "traceId", "details"}}

`register_exception_handlers(app)` 在 main.py 呼叫一次即可。
"""

import logging
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

log = logging.getLogger("app")


def _envelope(
    code: str,
    message: str,
    status_code: int,
    trace_id: str,
    details: dict | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "traceId": trace_id,
                "details": details,
            }
        },
    )


def _new_trace_id() -> str:
    return uuid.uuid4().hex[:12]


# 裸 HTTPException（未帶結構 detail）的 status → code 對照
_STATUS_CODE = {
    400: "bad_request",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    503: "not_configured",
}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exc_handler(request: Request, exc: HTTPException):
        trace_id = _new_trace_id()
        detail = exc.detail
        log.info(
            "HTTPException %s during %s %s [trace=%s]: %s",
            exc.status_code, request.method, request.url.path, trace_id, detail,
        )
        # 結構化 detail（來自 app.common.exceptions）：原樣轉信封
        if isinstance(detail, dict) and "code" in detail:
            return _envelope(
                code=detail["code"],
                message=detail.get("message", str(detail)),
                status_code=exc.status_code,
                trace_id=trace_id,
                details=detail.get("details"),
            )
        # 裸 HTTPException（如 raise HTTPException(404, "找不到")）：依 status 推 code
        return _envelope(
            code=_STATUS_CODE.get(exc.status_code, "http_error"),
            message=str(detail),
            status_code=exc.status_code,
            trace_id=trace_id,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exc_handler(request: Request, exc: RequestValidationError):
        trace_id = _new_trace_id()
        log.info(
            "Validation error during %s %s [trace=%s]: %s",
            request.method, request.url.path, trace_id, exc.errors(),
        )
        return _envelope(
            code="validation_error",
            message="Request validation failed",
            status_code=422,
            trace_id=trace_id,
            details={"errors": jsonable_encoder(exc.errors())},
        )

    @app.exception_handler(IntegrityError)
    async def integrity_exc_handler(request: Request, exc: IntegrityError):
        """DB 約束違反 → 409，而非不透明的 500。"""
        trace_id = _new_trace_id()
        log.info(
            "IntegrityError during %s %s [trace=%s]",
            request.method, request.url.path, trace_id,
        )
        return _envelope(
            code="conflict",
            message="資料衝突或違反約束",
            status_code=409,
            trace_id=trace_id,
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        """str(exc) 可能含 SQL／連線字串等敏感資訊，不回 client；server log 用同個
        trace_id 寫完整 traceback，client 報的 traceId 一定 grep 得到。"""
        trace_id = _new_trace_id()
        log.exception(
            "Unhandled exception during %s %s [trace=%s]: %s",
            request.method, request.url.path, trace_id, exc,
        )
        return _envelope(
            code="internal_error",
            message="伺服器發生未預期錯誤，請帶 traceId 聯絡維護者。",
            status_code=500,
            trace_id=trace_id,
        )
