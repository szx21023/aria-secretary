"""LINE Messaging API 用戶端：reply（回覆 token）與 push（主動推播）。

只包這兩個用得到的 endpoint，用 httpx 直打，不引整包 line-bot-sdk。
- reply：免費、不限量，但 reply token 用過即失效且有時效，故只在 webhook 當輪回覆用。
- push：可隨時主動送（排程推播靠它），但計入每月配額。

回傳布林表示 LINE 是否收下（2xx）。失敗只記 log 不拋——呼叫端（webhook 背景工作、
排程器）不該因單次送信失敗而中斷整個流程；對話與資料已先落地，重點是別把例外往上炸。
"""

import logging

import httpx

logger = logging.getLogger(__name__)

_REPLY_URL = "https://api.line.me/v2/bot/message/reply"
_PUSH_URL = "https://api.line.me/v2/bot/message/push"
_TIMEOUT = 10.0


def _headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }


def _text_messages(text: str) -> list[dict]:
    # LINE 單則文字上限 5000 字；秘書回覆極少超過，超過就截斷並留尾註而非讓 API 400。
    if len(text) > 5000:
        text = text[:4990] + "…（略）"
    return [{"type": "text", "text": text}]


async def reply(access_token: str, reply_token: str, text: str) -> bool:
    """用 webhook 帶來的 reply token 回覆一則文字。"""
    payload = {"replyToken": reply_token, "messages": _text_messages(text)}
    return await _post(_REPLY_URL, access_token, payload, kind="reply")


async def push(access_token: str, to_user_id: str, text: str) -> bool:
    """主動推播一則文字給指定 user。"""
    payload = {"to": to_user_id, "messages": _text_messages(text)}
    return await _post(_PUSH_URL, access_token, payload, kind="push")


async def _post(url: str, access_token: str, payload: dict, kind: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as http:
            resp = await http.post(url, headers=_headers(access_token), json=payload)
        if resp.status_code // 100 == 2:
            return True
        # LINE 把錯誤原因（如 reply token 失效、配額用盡）放在 body，記下來才 debug 得動。
        logger.warning("LINE %s 失敗 status=%s body=%s", kind, resp.status_code, resp.text)
        return False
    except Exception:
        logger.exception("LINE %s 請求例外", kind)
        return False
