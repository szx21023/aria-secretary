"""chat API 的歷史重建測試。

_load_history 負責把 DB 訊息轉成 Anthropic messages 格式，並滿足
「第一則必須是 user」的硬規則（剝掉開頭的 assistant，例如 seed 的問候）。
這段是 reschedule 後最容易默默 400 的 off-by-one，獨立測。
created_at 明確給遞增值，避免同次 commit 時間戳相等導致排序不穩。
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.api.chat import _load_history
from app.models.chat import Conversation, Message
from app.models.enums import MessageRole

pytestmark = pytest.mark.asyncio

_BASE = datetime(2026, 6, 5, 1, 0, tzinfo=timezone.utc)


async def _convo(db) -> Conversation:
    convo = Conversation(title="t")
    db.add(convo)
    await db.commit()
    await db.refresh(convo)
    return convo


async def _add(db, convo_id, role, content, minute):
    db.add(
        Message(
            conversation_id=convo_id,
            role=role,
            content=content,
            created_at=_BASE + timedelta(minutes=minute),
        )
    )


async def test_load_history_strips_leading_assistant(db):
    convo = await _convo(db)
    await _add(db, convo.id, MessageRole.assistant, "seed 問候", 1)
    await _add(db, convo.id, MessageRole.user, "嗨", 2)
    await _add(db, convo.id, MessageRole.assistant, "你好", 3)
    await db.commit()

    hist = await _load_history(db, convo.id)

    # 開頭 assistant 被剝掉，第一則必為 user
    assert [m["role"] for m in hist] == ["user", "assistant"]
    assert hist[0]["content"] == "嗨"


async def test_load_history_filters_empty_and_nonchat_roles(db):
    convo = await _convo(db)
    await _add(db, convo.id, MessageRole.user, "問題", 1)
    await _add(db, convo.id, MessageRole.assistant, "", 2)  # 空內容 → 剔除
    await _add(db, convo.id, MessageRole.tool, "工具輸出", 3)  # 非對話角色 → 剔除
    await _add(db, convo.id, MessageRole.assistant, "回答", 4)
    await db.commit()

    hist = await _load_history(db, convo.id)

    assert hist == [
        {"role": "user", "content": "問題"},
        {"role": "assistant", "content": "回答"},
    ]


async def test_load_history_empty_conversation(db):
    convo = await _convo(db)
    assert await _load_history(db, convo.id) == []
