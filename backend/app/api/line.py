"""LINE Messaging API webhook：在 LINE 上跟秘書對話。

流程：驗簽 → 立刻回 200（LINE 要求快速回應，逾時會重送）→ 背景跑 AI →
用 reply token 回覆（失敗則 fallback push）。對話與網頁共用同一個全域 conversation，
所以在 LINE 講的話、網頁也看得到，反之亦然。
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, status

from app.ai.agent import run_chat
from app.config import get_settings
from app.db import AsyncSessionLocal
from app.line import client
from app.line.signature import verify_signature
from app.services.conversation import (
    add_assistant_message,
    add_user_message,
    get_or_create_conversation,
    load_history,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/line", tags=["line"])

_FALLBACK_REPLY = "抱歉，我這邊出了點狀況，沒能處理你的訊息，等一下再試一次好嗎？"
_UNAUTHORIZED_REPLY = "抱歉，這個秘書只服務它的主人，沒辦法回應你的訊息。"


def _authorized(settings, user_id: str | None) -> bool:
    """白名單為空＝不限制；非空則 user_id 必須在名單內。

    沒驗哪個 LINE 使用者就放行，會讓任何加到 bot 的人都讀得到主人的行程與對話歷史，
    所以授權檢查擋在進對話之前——簽章只證明「訊息來自 LINE」，不代表「來自主人」。
    """
    allowed = settings.line_allowed_user_id_list
    if not allowed:
        return True
    return user_id in allowed


@router.post("/webhook")
async def webhook(
    request: Request,
    background: BackgroundTasks,
    x_line_signature: str | None = Header(default=None),
) -> dict[str, str]:
    settings = get_settings()
    if not settings.line_enabled:
        # 沒設定 LINE 還被打到：回 503 而非靜默 200，免得對方以為已串好。
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "LINE 未設定")

    # 簽章用「原始 bytes」重算，必須在任何 parse 之前取得。
    body = await request.body()
    if not verify_signature(settings.line_channel_secret, body, x_line_signature):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "簽章驗證失敗")

    payload = await request.json()
    for event in payload.get("events", []):
        # 只處理文字訊息；其他事件（貼圖、follow、加好友…）先略過。
        if event.get("type") != "message" or event.get("message", {}).get("type") != "text":
            continue
        reply_token = event.get("replyToken")
        user_id = event.get("source", {}).get("userId")
        text = event["message"]["text"]
        # 授權擋在最前面：未授權者不進對話，記下 userId（方便主人把自己加進白名單）並婉拒。
        if not _authorized(settings, user_id):
            logger.warning("LINE 訊息來自未授權 user=%s，已忽略", user_id)
            if reply_token:
                background.add_task(_decline, settings.line_channel_access_token, reply_token)
            continue
        # 背景處理：AI 可能跑數秒，不能卡住 webhook 回應（否則 LINE 逾時重送 → 重複回覆）。
        background.add_task(_handle_text, text, reply_token, user_id)

    return {"status": "ok"}


async def _decline(token: str, reply_token: str) -> None:
    await client.reply(token, reply_token, _UNAUTHORIZED_REPLY)


async def _handle_text(text: str, reply_token: str | None, user_id: str | None) -> None:
    """背景：存訊息→跑 AI→存回覆→回 LINE。獨立 session（request 已結束）。"""
    settings = get_settings()
    token = settings.line_channel_access_token
    try:
        async with AsyncSessionLocal() as db:
            convo = await get_or_create_conversation(db)
            # 記下這位使用者當作推播預設收件人（沒設定 line_push_user_id 時用它）。
            if user_id and convo.line_user_id != user_id:
                convo.line_user_id = user_id
                await db.commit()

            history = await load_history(db, convo.id)
            add_user_message(db, convo.id, text)
            await db.commit()

            reply_text = await run_chat(db, history, text)
            if reply_text:
                add_assistant_message(db, convo.id, reply_text)
                await db.commit()
            else:
                # 模型整輪沒吐字（非例外，例如只呼叫工具就收尾）。留 log 區分於真失敗，仍給 fallback。
                logger.warning("LINE 對話模型回覆為空，改送 fallback")
                reply_text = _FALLBACK_REPLY

        await _send(token, reply_token, user_id, reply_text)
    except Exception:
        # AI 或 DB 爆掉也要讓使用者收到「失敗」訊息，而不是已讀不回。
        logger.exception("LINE 訊息處理失敗")
        await _send(token, reply_token, user_id, _FALLBACK_REPLY)


async def _send(token: str, reply_token: str | None, user_id: str | None, text: str) -> None:
    """優先用 reply token（免費、不限量）；失敗（逾時/用過）再 fallback push。"""
    if reply_token and await client.reply(token, reply_token, text):
        return
    if user_id and await client.push(token, user_id, text):
        return
    # 兩條路都送不出去（reply 失敗且沒有可 push 的對象）：明確記一筆，否則訊息靜默蒸發。
    logger.warning("LINE 訊息無法送達（reply 失敗、無 push 對象）")
