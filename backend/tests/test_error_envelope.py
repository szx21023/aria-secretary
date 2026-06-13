"""統一錯誤信封：所有錯誤回應都是 {"error": {code, message, traceId, details}}。

只驗信封結構與 code/status 對應；各端點的 status code 由各自測試覆蓋。
"""

import pytest

pytestmark = pytest.mark.asyncio


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
