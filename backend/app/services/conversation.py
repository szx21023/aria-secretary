"""對話持久化的共用邏輯：取得/建立全域 conversation、載入歷史、存訊息。

web 的 SSE chat（api/chat.py）與 LINE webhook（api/line.py）都靠這裡，
避免兩條入口各寫一份「載歷史→存 user→跑 AI→存 assistant」而漂移。
MVP 為單一全域 conversation（單人），LINE 與網頁共用同一段記憶。
"""

import math

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.chat import Conversation, Message
from app.models.enums import MessageRole

# 歷史超過上限時一次捨棄的則數；取偶數讓截斷點盡量落在 user 訊息上
HISTORY_TRIM_STEP = 10


async def get_or_create_conversation(db: AsyncSession) -> Conversation:
    """取最早建立的 conversation；沒有就建一個（全域單一）。"""
    convo = await db.scalar(select(Conversation).order_by(Conversation.created_at).limit(1))
    if convo is None:
        convo = Conversation(title="Aria")
        db.add(convo)
        await db.commit()
        await db.refresh(convo)
    return convo


async def load_history(db: AsyncSession, convo_id: str, max_messages: int | None = None) -> list[dict]:
    """把已存的 user/assistant 文字訊息轉成 Anthropic messages 格式。

    超過 max_messages（預設取 settings.history_max_messages）時，從最舊的訊息以
    HISTORY_TRIM_STEP 則為單位整段捨棄，而非每輪滑動一則：這樣連續幾輪送出的開頭相同，
    prompt cache 才命中得了。保留的則數因此約在 max_messages - HISTORY_TRIM_STEP 到 max_messages 之間
    （截斷後若再剝掉開頭的 assistant，會再少一則）。
    Anthropic 要求 messages 第一則為 user，所以去掉開頭的 assistant（例如 seed 的問候，
    或截斷後落在開頭的回覆）。
    """
    limit = get_settings().history_max_messages if max_messages is None else max_messages
    # 過濾與計數都交給 DB：對話會無限累積，不能每輪把整條撈進記憶體只為了取最後幾十則。
    chat_message_filters = (
        Message.conversation_id == convo_id,
        Message.role.in_((MessageRole.user, MessageRole.assistant)),
        Message.content != "",
    )
    total = await db.scalar(select(func.count()).select_from(Message).where(*chat_message_filters)) or 0
    rows = await db.scalars(
        select(Message).where(*chat_message_filters).order_by(Message.created_at).offset(_trim_offset(total, limit))
    )
    history = [{"role": message.role.value, "content": message.content} for message in rows]
    while history and history[0]["role"] == MessageRole.assistant.value:
        history.pop(0)
    return history


def _trim_offset(total: int, limit: int) -> int:
    """超過 limit 時要從最舊捨棄幾則：以 HISTORY_TRIM_STEP 為單位整段捨棄，只由總則數決定。"""
    overflow = total - limit
    if overflow <= 0:
        return 0
    step = max(1, min(HISTORY_TRIM_STEP, limit))
    return math.ceil(overflow / step) * step


def add_user_message(db: AsyncSession, convo_id: str, content: str) -> None:
    db.add(Message(conversation_id=convo_id, role=MessageRole.user, content=content))


def add_assistant_message(db: AsyncSession, convo_id: str, content: str) -> None:
    db.add(Message(conversation_id=convo_id, role=MessageRole.assistant, content=content))
