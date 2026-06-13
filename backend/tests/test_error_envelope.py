"""統一錯誤信封：所有錯誤回應都是 {"error": {code, message, traceId, details}}。

只驗信封結構與 code/status 對應；各端點的 status code 由各自測試覆蓋。
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.common.exceptions import NotFoundException
from app.main import app

pytestmark = pytest.mark.asyncio

_SECRET = "postgres://user:pa55w0rd@db.internal/secret"


# 臨時路由，專供測信封：未捕捉例外（500）與結構化例外（details 透傳）。
@app.get("/api/_test/boom")
async def _boom():
    raise RuntimeError(_SECRET)  # 模擬內部例外，訊息含敏感字串


@app.get("/api/_test/notfound-details")
async def _notfound_details():
    raise NotFoundException("沒這東西", details={"id": "abc123"})


async def test_not_found_uses_envelope(client):
    resp = await client.get("/api/tasks/nope")
    assert resp.status_code == 404
    err = resp.json()["error"]
    assert err["code"] == "not_found"
    assert err["message"]  # 有人看得懂的訊息
    assert err["traceId"]  # 一定帶 traceId 可對 log


async def test_validation_error_uses_envelope(client):
    # title 缺漏 → 422
    resp = await client.post("/api/tasks", json={})
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "validation_error"
    assert err["traceId"]
    assert err["details"]["errors"]  # 帶 pydantic 驗證細節


async def test_structured_exception_passes_through_details(client):
    # NotFoundException 走 handler 的結構化分支：code 與 details 都要原樣透傳
    resp = await client.get("/api/_test/notfound-details")
    assert resp.status_code == 404
    err = resp.json()["error"]
    assert err["code"] == "not_found"
    assert err["details"] == {"id": "abc123"}


async def test_unhandled_exception_500_does_not_leak():
    # ServerErrorMiddleware 預設會把 500 往 transport 重拋，故關掉 raise_app_exceptions
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/_test/boom")
    assert resp.status_code == 500
    err = resp.json()["error"]
    assert err["code"] == "internal_error"
    assert err["traceId"]
    # 內部例外字串（含 DB 連線字串）不可外洩給 client
    assert _SECRET not in resp.text
    assert "pa55w0rd" not in resp.text
