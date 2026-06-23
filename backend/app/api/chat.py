import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agent import stream_chat
from app.db import AsyncSessionLocal, get_db
from app.models.chat import Message
from app.models.enums import MessageRole
from app.schemas.chat import ChatEvent, ChatRequest, MessageRead
from app.services.conversation import (
    add_assistant_message,
    add_user_message,
    get_or_create_conversation,
    load_history,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _sse(event: ChatEvent) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("")
async def chat(payload: ChatRequest) -> StreamingResponse:
    async def gen():
        # StreamingResponse 的 generator 在 request handler 回傳後才執行，
        # 此時 request 級 get_db session 已關閉，故串流改用獨立 session。
        async with AsyncSessionLocal() as db:
            convo = await get_or_create_conversation(db)
            history = await load_history(db, convo.id)

            add_user_message(db, convo.id, payload.message)
            await db.commit()

            streamed = ""
            saved = False
            try:
                async for ev in stream_chat(db, history, payload.message):
                    if ev["type"] == "delta":
                        streamed += ev["text"]
                    elif ev["type"] == "done":
                        content = ev["text"] or streamed.strip()
                        if content:  # 不存空泡泡
                            add_assistant_message(db, convo.id, content)
                            await db.commit()
                        saved = True
                    yield _sse(ev)
            except Exception as e:  # noqa: BLE001 — 串流中任何錯誤都回報前端 + 留 log，而非靜默
                logger.exception("chat stream 失敗 (convo=%s)", convo.id)
                # 已串給使用者看的部分回覆要存下來，避免 reload 後憑空消失。
                # 復原存檔自己包 try：此時 DB 可能也在故障態，commit 再爆不能把 error frame 一起吞掉。
                try:
                    if streamed.strip() and not saved:
                        add_assistant_message(db, convo.id, streamed.strip())
                        await db.commit()
                except Exception:
                    logger.exception("error 復原存檔也失敗 (convo=%s)", convo.id)
                    await db.rollback()  # 對齊 get_db 慣例：別讓 session 帶著未結束交易離開
                yield _sse({"type": "error", "message": f"{type(e).__name__}: {e}"})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/history", response_model=list[MessageRead])
async def history(db: AsyncSession = Depends(get_db)) -> list[Message]:
    convo = await get_or_create_conversation(db)
    rows = await db.scalars(select(Message).where(Message.conversation_id == convo.id).order_by(Message.created_at))
    return [m for m in rows if m.role in (MessageRole.user, MessageRole.assistant)]
