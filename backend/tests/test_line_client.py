"""LINE API client 的送信契約：2xx→True、非 2xx→False、httpx 例外→False（不外拋）。

這層是整個韌性故事的根：reply/push 一律回 bool，呼叫端（webhook 背景工作、排程器）
才能在送信失敗時走 fallback / 重試，而不是被例外炸掉。用假的 httpx client 驗證三條路。
"""

import pytest

from app.line import client

pytestmark = pytest.mark.asyncio


class _FakeResp:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text


class _FakeHTTP:
    """模擬 httpx.AsyncClient：記錄 post 參數，回傳預設 resp 或拋例外。"""

    calls: list[dict] = []

    def __init__(self, resp=None, exc=None):
        self._resp = resp
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers, json):
        _FakeHTTP.calls.append({"url": url, "headers": headers, "json": json})
        if self._exc:
            raise self._exc
        return self._resp


def _patch_http(monkeypatch, resp=None, exc=None):
    _FakeHTTP.calls = []
    monkeypatch.setattr(client.httpx, "AsyncClient", lambda timeout: _FakeHTTP(resp=resp, exc=exc))


async def test_reply_2xx_returns_true_with_correct_payload(monkeypatch):
    _patch_http(monkeypatch, resp=_FakeResp(200))
    ok = await client.reply("tok", "rTok", "你好")
    assert ok is True
    call = _FakeHTTP.calls[0]
    assert call["url"].endswith("/message/reply")
    assert call["headers"]["Authorization"] == "Bearer tok"
    assert call["json"]["replyToken"] == "rTok"
    assert call["json"]["messages"] == [{"type": "text", "text": "你好"}]


async def test_push_2xx_returns_true(monkeypatch):
    _patch_http(monkeypatch, resp=_FakeResp(200))
    ok = await client.push("tok", "U1", "提醒")
    assert ok is True
    assert _FakeHTTP.calls[0]["json"]["to"] == "U1"


async def test_non_2xx_returns_false(monkeypatch):
    # 400/401/429（token 失效、配額用盡）→ False，讓呼叫端 fallback，而非當成功
    _patch_http(monkeypatch, resp=_FakeResp(429, text="rate limited"))
    assert await client.push("tok", "U1", "x") is False


async def test_httpx_exception_returns_false_not_raised(monkeypatch):
    # 連線/逾時例外不可外拋，否則背景工作與排程器會被炸斷
    _patch_http(monkeypatch, exc=RuntimeError("connection reset"))
    assert await client.reply("tok", "rTok", "x") is False


async def test_long_text_is_truncated(monkeypatch):
    _patch_http(monkeypatch, resp=_FakeResp(200))
    await client.push("tok", "U1", "字" * 6000)
    sent = _FakeHTTP.calls[0]["json"]["messages"][0]["text"]
    assert len(sent) <= 5000
    assert sent.endswith("…（略）")
