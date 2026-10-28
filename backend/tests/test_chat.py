"""chat API 的歷史重建測試。

_load_history 負責把 DB 訊息轉成 Anthropic messages 格式，並滿足
「第一則必須是 user」的硬規則（剝掉開頭的 assistant，例如 seed 的問候）。
這段是 reschedule 後最容易默默 400 的 off-by-one，獨立測。
created_at 明確給遞增值，避免同次 commit 時間戳相等導致排序不穩。
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.models.chat import Conversation, Message
from app.models.enums import MessageRole
from app.services.conversation import _trim_offset
from app.services.conversation import load_history as _load_history

pytestmark = pytest.mark.asyncio

_BASE = datetime(2026, 6, 5, 1, 0, tzinfo=UTC)


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


async def _add_turns(db, convo_id, count):
    """依序寫入 count 則交替的 user/assistant 訊息，內容為 u0、a1、u2…（數字即寫入順序）。"""
    for index in range(count):
        role = MessageRole.user if index % 2 == 0 else MessageRole.assistant
        await _add(db, convo_id, role, f"{role.value[0]}{index}", index)
    await db.commit()


async def test_load_history_under_limit_keeps_all(db):
    convo = await _convo(db)
    await _add_turns(db, convo.id, 6)

    hist = await _load_history(db, convo.id, max_messages=6)

    assert [m["content"] for m in hist] == ["u0", "a1", "u2", "a3", "u4", "a5"]


@pytest.mark.parametrize(("total", "first_kept", "kept"), [(41, "u10", 31), (50, "u10", 40), (51, "u20", 31)])
async def test_load_history_trims_oldest_in_steps(db, total, first_kept, kept):
    convo = await _convo(db)
    await _add_turns(db, convo.id, total)

    hist = await _load_history(db, convo.id, max_messages=40)

    # 41～50 則都從同一點切（u10 起），開頭不變 → prompt cache 可連續命中；第 51 則才再切一段
    assert hist[0]["content"] == first_kept
    assert hist[-1]["content"].endswith(str(total - 1))
    assert len(hist) == kept


async def test_load_history_trim_strips_leading_assistant(db):
    convo = await _convo(db)
    await _add(db, convo.id, MessageRole.assistant, "seed 問候", 0)  # 開頭多一則 → 截斷點落在 assistant
    for index in range(1, 12):
        role = MessageRole.user if index % 2 == 1 else MessageRole.assistant
        await _add(db, convo.id, role, f"m{index}", index)
    await db.commit()

    hist = await _load_history(db, convo.id, max_messages=10)

    # 12 則超出 2 → 捨棄 10 則，切點落在 m10（assistant），剝掉後只剩 m11
    assert hist == [{"role": "user", "content": "m11"}]


async def test_load_history_defaults_to_settings_limit(db, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "history_max_messages", 2)
    convo = await _convo(db)
    await _add_turns(db, convo.id, 5)

    hist = await _load_history(db, convo.id)

    assert [m["content"] for m in hist] == ["u4"]


@pytest.mark.parametrize(
    ("total", "limit", "expected"),
    [(40, 40, 0), (41, 40, 10), (50, 40, 10), (51, 40, 20), (5, 2, 4), (3, 0, 3)],
)
async def test_trim_offset_drops_in_steps(total, limit, expected):
    # 純函式，宣告 async 只為配合本檔的 pytestmark。
    # 上限小於 HISTORY_TRIM_STEP 時以上限為單位；上限 0 時全部捨棄、不能除以零
    assert _trim_offset(total, limit) == expected


async def test_load_history_skips_trimmed_rows_in_db(db):
    # 對話無限累積：要捨棄的舊訊息由 DB 用 OFFSET 跳過，不能整條撈出來再在 Python 切
    from sqlalchemy import event

    convo = await _convo(db)
    await _add_turns(db, convo.id, 51)
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    sync_engine = db.bind.sync_engine
    event.listen(sync_engine, "before_cursor_execute", record)
    try:
        hist = await _load_history(db, convo.id, max_messages=40)
    finally:
        event.remove(sync_engine, "before_cursor_execute", record)

    assert len(hist) == 31
    row_selects = [sql for sql in statements if "count(" not in sql.lower()]
    assert len(row_selects) == 1
    assert "OFFSET" in row_selects[0].upper()
