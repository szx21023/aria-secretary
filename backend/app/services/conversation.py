"""對話持久化的共用邏輯：取得/建立全域 conversation、載入歷史、存訊息。

web 的 SSE chat（api/chat.py）與 LINE webhook（api/line.py）都靠這裡，
避免兩條入口各寫一份「載歷史→存 user→跑 AI→存 assistant」而漂移。
MVP 為單一全域 conversation（單人），LINE 與網頁共用同一段記憶。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import Conversation, Message
from app.models.enums import MessageRole


async def get_or_create_conversation(db: AsyncSession) -> Conversation:
    """取最早建立的 conversation；沒有就建一個（全域單一）。"""
    convo = await db.scalar(select(Conversation).order_by(Conversation.created_at).limit(1))
    if convo is None:
        convo = Conversation(title="Aria")
        db.add(convo)
        await db.commit()
        await db.refresh(convo)
    return convo


async def load_history(db: AsyncSession, convo_id: str) -> list[dict]:
    """把已存的 user/assistant 文字訊息轉成 Anthropic messages 格式。

    Anthropic 要求 messages 第一則為 user，所以去掉開頭的 assistant（例如 seed 的問候）。
    """
    rows = await db.scalars(
        select(Message)
        .where(Message.conversation_id == convo_id)
        .order_by(Message.created_at)
    )
    hist = [
        {"role": m.role.value, "content": m.content}
        for m in rows
        if m.role in (MessageRole.user, MessageRole.assistant) and m.content
    ]
    while hist and hist[0]["role"] == "assistant":
        hist.pop(0)
    return hist


def add_user_message(db: AsyncSession, convo_id: str, content: str) -> None:
    db.add(Message(conversation_id=convo_id, role=MessageRole.user, content=content))


def add_assistant_message(db: AsyncSession, convo_id: str, content: str) -> None:
    db.add(Message(conversation_id=convo_id, role=MessageRole.assistant, content=content))
