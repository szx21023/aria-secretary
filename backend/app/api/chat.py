import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agent import stream_chat
from app.db import AsyncSessionLocal, get_db
from app.models.chat import Conversation, Message
from app.models.enums import MessageRole
from app.schemas.chat import ChatRequest, MessageRead

router = APIRouter(prefix="/api/chat", tags=["chat"])


async def _get_or_create_conversation(db: AsyncSession) -> Conversation:
    convo = await db.scalar(select(Conversation).order_by(Conversation.created_at).limit(1))
    if convo is None:
        convo = Conversation(title="Aria")
        db.add(convo)
        await db.commit()
        await db.refresh(convo)
    return convo


async def _load_history(db: AsyncSession, convo_id: str) -> list[dict]:
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


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("")
async def chat(payload: ChatRequest) -> StreamingResponse:
    async def gen():
        # 串流期間用獨立 session，不依賴 request 級 session 的生命週期
        async with AsyncSessionLocal() as db:
            convo = await _get_or_create_conversation(db)
            history = await _load_history(db, convo.id)

            db.add(
                Message(conversation_id=convo.id, role=MessageRole.user, content=payload.message)
            )
            await db.commit()

            try:
                async for ev in stream_chat(db, history, payload.message):
                    if ev["type"] == "done":
                        db.add(
                            Message(
                                conversation_id=convo.id,
                                role=MessageRole.assistant,
                                content=ev["text"],
                            )
                        )
                        await db.commit()
                    yield _sse(ev)
            except Exception as e:  # noqa: BLE001 — 串流中任何錯誤都回報給前端而非靜默
                yield _sse({"type": "error", "message": f"{type(e).__name__}: {e}"})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/history", response_model=list[MessageRead])
async def history(db: AsyncSession = Depends(get_db)) -> list[Message]:
    convo = await _get_or_create_conversation(db)
    rows = await db.scalars(
        select(Message)
        .where(Message.conversation_id == convo.id)
        .order_by(Message.created_at)
    )
    return [m for m in rows if m.role in (MessageRole.user, MessageRole.assistant)]
