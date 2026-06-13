"""LINE webhook 端點：未設定→503、簽章錯→403、簽章對→200 並把文字訊息排入背景處理。

不打真 AI / 真 LINE：背景處理函式 _handle_text 被換成記錄器，只驗證「收到對的事件、
帶對的參數排程」這層契約。AI 與送信路徑分別在 test_agent / _send 單元測試覆蓋。
"""

import base64
import hashlib
import hmac
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api import line
from app.models.base import Base
from app.models.chat import Conversation, Message
from app.models.enums import MessageRole

pytestmark = pytest.mark.asyncio

_SECRET = "sec"


def _fake_settings(enabled=True, allowed=None):
    return SimpleNamespace(
        line_enabled=enabled,
        line_channel_secret=_SECRET,
        line_channel_access_token="tok",
        line_allowed_user_id_list=allowed or [],  # 預設空＝不限制
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


async def test_webhook_blocks_unauthorized_user(client, monkeypatch):
    # 白名單非空、訊息來自名單外的人 → 不進對話處理、改送婉拒
    monkeypatch.setattr(line, "get_settings", lambda: _fake_settings(allowed=["Uowner"]))
    handled, declined = [], []
    monkeypatch.setattr(line, "_handle_text", lambda *a: handled.append(a))

    async def fake_decline(token, reply_token):
        declined.append(reply_token)

    monkeypatch.setattr(line, "_decline", fake_decline)

    body = _text_event("今天有什麼行程", reply_token="rTok", user_id="Ustranger")
    resp = await client.post("/api/line/webhook", content=body, headers={"X-Line-Signature": _sign(body)})

    assert resp.status_code == 200
    assert handled == []  # 未授權者讀不到主人的資料
    assert declined == ["rTok"]


async def test_webhook_allows_listed_user(client, monkeypatch):
    monkeypatch.setattr(line, "get_settings", lambda: _fake_settings(allowed=["Uowner"]))
    handled = []
    monkeypatch.setattr(line, "_handle_text", lambda *a: handled.append(a))

    body = _text_event("今天有什麼行程", reply_token="rTok", user_id="Uowner")
    resp = await client.post("/api/line/webhook", content=body, headers={"X-Line-Signature": _sign(body)})

    assert resp.status_code == 200
    assert handled == [("今天有什麼行程", "rTok", "Uowner")]


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


async def test_decline_sends_unauthorized_reply(monkeypatch):
    # _decline 的本體（webhook 測試把它 stub 掉了）：用 reply 送婉拒訊息，
    # 且參數順序為 (token, reply_token, text)——順序錯了所有 webhook 測試照樣綠，所以在這裡釘死。
    sent = []

    async def fake_reply(token, reply_token, text):
        sent.append((token, reply_token, text))
        return True

    monkeypatch.setattr(line.client, "reply", fake_reply)

    await line._decline("tok", "rTok")
    assert sent == [("tok", "rTok", line._UNAUTHORIZED_REPLY)]


# ── _handle_text 背景處理：用 in-memory DB 取代獨立 session ─────────

@pytest_asyncio.fixture
async def line_db(monkeypatch):
    """讓 _handle_text 的 AsyncSessionLocal 指向一個共享的 in-memory 庫。"""
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(line, "AsyncSessionLocal", maker)
    monkeypatch.setattr(line, "get_settings", lambda: _fake_settings())
    yield maker
    await engine.dispose()


async def _messages(maker) -> list[tuple]:
    async with maker() as db:
        rows = await db.scalars(select(Message).order_by(Message.created_at))
        return [(m.role, m.content) for m in rows]


async def test_handle_text_persists_and_captures_user_id(line_db, monkeypatch):
    sent = []

    async def fake_run_chat(db, history, text):
        return "好，加進待辦了"

    async def fake_send(token, reply_token, user_id, text):
        sent.append((reply_token, user_id, text))

    monkeypatch.setattr(line, "run_chat", fake_run_chat)
    monkeypatch.setattr(line, "_send", fake_send)

    await line._handle_text("幫我加待辦", "rTok", "Uxyz")

    # 回覆只送一次、帶真回覆
    assert sent == [("rTok", "Uxyz", "好，加進待辦了")]
    # user + assistant 訊息都落地
    assert await _messages(line_db) == [
        (MessageRole.user, "幫我加待辦"),
        (MessageRole.assistant, "好，加進待辦了"),
    ]
    # line_user_id 被捕捉（推播預設收件人靠它）
    async with line_db() as db:
        convo = await db.scalar(select(Conversation))
        assert convo.line_user_id == "Uxyz"


async def test_handle_text_empty_reply_sends_fallback_without_persisting(line_db, monkeypatch):
    sent = []

    async def empty_run_chat(db, history, text):
        return ""  # 模型整輪沒吐字

    async def fake_send(token, reply_token, user_id, text):
        sent.append(text)

    monkeypatch.setattr(line, "run_chat", empty_run_chat)
    monkeypatch.setattr(line, "_send", fake_send)

    await line._handle_text("嗨", "rTok", "U1")

    assert sent == [line._FALLBACK_REPLY]
    # 空回覆不存 assistant 泡泡，只留 user 訊息
    assert await _messages(line_db) == [(MessageRole.user, "嗨")]


async def test_handle_text_exception_sends_fallback(line_db, monkeypatch):
    sent = []

    async def boom(db, history, text):
        raise RuntimeError("AI 爆了")

    async def fake_send(token, reply_token, user_id, text):
        sent.append(text)

    monkeypatch.setattr(line, "run_chat", boom)
    monkeypatch.setattr(line, "_send", fake_send)

    await line._handle_text("嗨", "rTok", "U1")

    # 例外也要送 fallback（不是已讀不回），且只送一次
    assert sent == [line._FALLBACK_REPLY]
