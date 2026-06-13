"""跨模組共用 HTTP 例外 — 端點/service 直接 raise，由 exception_handlers.py 包成 envelope。

detail 帶 {code, message, details}，handler 認得這個結構就原樣轉成回應信封；
沒帶結構的裸 HTTPException 也能 fallback（見 exception_handlers）。
"""

from fastapi import HTTPException


class NotFoundException(HTTPException):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(
            status_code=404,
            detail={"code": "not_found", "message": message, "details": details},
        )


class BadRequestException(HTTPException):
    """請求語意有誤（例如引用了不存在的 id、欄位被設成不允許的 null）。"""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(
            status_code=400,
            detail={"code": "bad_request", "message": message, "details": details},
        )


class ConfigException(HTTPException):
    """伺服器缺少必要設定（例如 LINE 未設定）。"""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(
            status_code=503,
            detail={"code": "not_configured", "message": message, "details": details},
        )


class UpstreamException(HTTPException):
    """上游服務（例如 Anthropic）呼叫失敗或回傳異常。"""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(
            status_code=502,
            detail={"code": "upstream_error", "message": message, "details": details},
        )
