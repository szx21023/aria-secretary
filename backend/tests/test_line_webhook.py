"""LINE webhook 端點：未設定→503、簽章錯→403、簽章對→200 並把文字訊息排入背景處理。

不打真 AI / 真 LINE：背景處理函式 _handle_text 被換成記錄器，只驗證「收到對的事件、
帶對的參數排程」這層契約。AI 與送信路徑分別在 test_agent / _send 單元測試覆蓋。
"""

import base64
import hashlib
import hmac
from types import SimpleNamespace

import pytest

from app.api import line

pytestmark = pytest.mark.asyncio

_SECRET = "sec"


def _fake_settings(enabled=True):
    return SimpleNamespace(
        line_enabled=enabled,
        line_channel_secret=_SECRET,
        line_channel_access_token="tok",
    )


def _sign(body: bytes) -> str:
    return base64.b64encode(hmac.new(_SECRET.encode(), body, hashlib.sha256).digest()).decode()


def _text_event(text: str, reply_token="r1", user_id="U123") -> bytes:
    import json

    payload = {
        "events": [
            {
                "type": "message",
                "replyToken": reply_token,
                "source": {"type": "user", "userId": user_id},
                "message": {"type": "text", "text": text},
            }
        ]
    }
    return json.dumps(payload).encode()


async def test_webhook_503_when_disabled(client, monkeypatch):
    monkeypatch.setattr(line, "get_settings", lambda: _fake_settings(enabled=False))
    body = _text_event("嗨")
    resp = await client.post("/api/line/webhook", content=body, headers={"X-Line-Signature": _sign(body)})
    assert resp.status_code == 503


async def test_webhook_rejects_bad_signature(client, monkeypatch):
    monkeypatch.setattr(line, "get_settings", lambda: _fake_settings())
    body = _text_event("嗨")
    resp = await client.post("/api/line/webhook", content=body, headers={"X-Line-Signature": "bad"})
    assert resp.status_code == 403


async def test_webhook_accepts_valid_and_enqueues(client, monkeypatch):
    monkeypatch.setattr(line, "get_settings", lambda: _fake_settings())
    calls = []

    async def fake_handle(text, reply_token, user_id):
        calls.append((text, reply_token, user_id))

    monkeypatch.setattr(line, "_handle_text", fake_handle)

    body = _text_event("幫我加個待辦", reply_token="rTok", user_id="Uabc")
    resp = await client.post("/api/line/webhook", content=body, headers={"X-Line-Signature": _sign(body)})

    assert resp.status_code == 200
    assert calls == [("幫我加個待辦", "rTok", "Uabc")]


async def test_webhook_ignores_nontext_events(client, monkeypatch):
    monkeypatch.setattr(line, "get_settings", lambda: _fake_settings())
    calls = []
    monkeypatch.setattr(line, "_handle_text", lambda *a: calls.append(a))

    import json

    body = json.dumps({"events": [{"type": "follow", "source": {"userId": "U1"}}]}).encode()
    resp = await client.post("/api/line/webhook", content=body, headers={"X-Line-Signature": _sign(body)})

    assert resp.status_code == 200
    assert calls == []  # follow 事件不進對話處理


async def test_send_prefers_reply_then_falls_back_to_push(monkeypatch):
    # reply 成功 → 不 push
    sent = {"reply": [], "push": []}

    async def fake_reply(token, reply_token, text):
        sent["reply"].append((reply_token, text))
        return True

    async def fake_push(token, user_id, text):
        sent["push"].append((user_id, text))
        return True

    monkeypatch.setattr(line.client, "reply", fake_reply)
    monkeypatch.setattr(line.client, "push", fake_push)

    await line._send("tok", "rTok", "U1", "回覆")
    assert sent["reply"] == [("rTok", "回覆")]
    assert sent["push"] == []


async def test_send_falls_back_to_push_when_reply_fails(monkeypatch):
    sent = {"push": []}

    async def fake_reply(token, reply_token, text):
        return False  # token 失效/逾時

    async def fake_push(token, user_id, text):
        sent["push"].append((user_id, text))
        return True

    monkeypatch.setattr(line.client, "reply", fake_reply)
    monkeypatch.setattr(line.client, "push", fake_push)

    await line._send("tok", "rTok", "U1", "回覆")
    assert sent["push"] == [("U1", "回覆")]
