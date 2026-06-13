"""跨模組共用 HTTP 例外 — 端點直接 raise，由 exception_handlers.py 包成 envelope。

detail 帶 {code, message, details}，handler 認得這個結構就原樣轉成回應信封。
目前只有 NotFoundException 有實際用到；其餘需要時再依同一模式新增（不預先囤積死碼）。
"""

from fastapi import HTTPException


class NotFoundException(HTTPException):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(
            status_code=404,
            detail={"code": "not_found", "message": message, "details": details},
        )
