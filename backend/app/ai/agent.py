"""串流式 agentic loop：手動處理 tool-use 迴圈，逐字串流回前端。

採手動 loop（非 SDK tool_runner）以便：逐 token 串流、攔每個 tool call 推 SSE、之後加權限控制。
"""

import logging
from collections.abc import AsyncGenerator
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import MODEL, get_client
from app.ai.executor import run_tool
from app.ai.system_prompt import SYSTEM_PROMPT
from app.ai.tools import TOOLS
from app.config import get_settings
from app.schemas.chat import ChatEvent

logger = logging.getLogger(__name__)

_TZ = ZoneInfo(get_settings().app_tz)
MAX_TOOL_ROUNDS = 5  # 安全上限；用完仍在 tool_use 就停，避免無限迴圈


def _now_context() -> str:
    now = datetime.now(_TZ)
    week = "一二三四五六日"[now.weekday()]
    return f"（目前時間：{now.strftime('%Y-%m-%d %H:%M')} 星期{week}）"


async def stream_chat(db: AsyncSession, history: list[dict], user_text: str) -> AsyncGenerator[ChatEvent, None]:
    """逐步 yield SSE 事件（型別見 schemas.chat.ChatEvent）。"""
    client = get_client()
    # 動態情境（現在時間）走 message 層，不污染 system，保住 prompt cache 前綴
    messages: list[dict] = [
        *history,
        {"role": "user", "content": f"{_now_context()}\n{user_text}"},
    ]
    full_text = ""
    hit_cap = True  # 若迴圈正常 break（模型給出最終回覆）會改 False

    for _ in range(MAX_TOOL_ROUNDS):
        async with client.messages.stream(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            messages=messages,
        ) as stream:
            async for event in stream:
                if event.type == "content_block_delta" and event.delta.type == "text_delta":
                    full_text += event.delta.text
                    yield {"type": "delta", "text": event.delta.text}
            final = await stream.get_final_message()

        if final.stop_reason != "tool_use":
            hit_cap = False
            break

        # 保留整段 assistant content（含 thinking 與 tool_use，簽章必須原樣回灌），執行工具後回灌
        messages.append({"role": "assistant", "content": final.content})
        tool_results = []
        for block in final.content:
            if block.type == "tool_use":
                # 成功路徑也留痕：日後 debug「為何回了奇怪的答案」才知道工具有沒有被呼叫、帶了什麼參數
                logger.info("tool call: %s args=%s", block.name, block.input or {})
                yield {"type": "tool", "name": block.name}
                # 工具執行失敗（DB 錯誤、未預期例外）回成 is_error 的 tool_result，
                # 讓模型知道失敗並自我修正，而不是讓整輪對話死在 broad except。
                try:
                    result = await run_tool(db, block.name, block.input or {})
                    tr = {"type": "tool_result", "tool_use_id": block.id, "content": result.text}
                    # 工具真的改了資料才推 state_changed，讓前端只重抓受影響的 query
                    if result.changed:
                        yield {"type": "state_changed", "resource": result.changed}
                except Exception as e:
                    # 工具若 commit 到一半失敗，整段串流共用的 session 會進 pending-rollback；
                    # 先 rollback 讓它對同輪後續工具與最後存 assistant 訊息仍可用，
                    # 否則單一暫時性錯誤會 cascade 成一連串 PendingRollbackError、整輪回覆遺失。
                    # rollback 自己也包起來：連 rollback 都爆也不能讓例外逸出 stream、吞掉 error frame 與原始錯誤。
                    try:
                        await db.rollback()
                    except Exception:
                        logger.exception("tool %s 失敗後 rollback 也失敗", block.name)
                    logger.exception("tool %s 執行失敗", block.name)
                    tr = {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": f"工具執行失敗：{e}",
                        "is_error": True,
                    }
                tool_results.append(tr)
        messages.append({"role": "user", "content": tool_results})

    text = full_text.strip()
    if hit_cap:
        # 用盡輪數一律記一筆：就算已有部分文字，也代表模型其實沒收尾，別讓它和正常回覆在 log 裡長一樣
        logger.warning("tool round cap (%d) 用盡（text_len=%d）", MAX_TOOL_ROUNDS, len(text))
    if hit_cap and not text:
        # 連一個字都沒生出來 → 別吐空泡泡，給可重試的提示
        text = "這次的查詢有點複雜，我沒能整理出完整回覆，可以換個方式再問一次嗎？"
    yield {"type": "done", "text": text}


async def run_chat(db: AsyncSession, history: list[dict], user_text: str) -> str:
    """非串流入口：跑完整 agentic loop，只回最終文字。

    LINE 之類無法逐字串流的通道用它。內部 drain stream_chat，維持 agentic loop 單一來源——
    工具執行、衝突偵測、輪數上限與錯誤復原全部沿用，不另寫一套。
    """
    final_text = ""
    async for ev in stream_chat(db, history, user_text):
        if ev["type"] == "done":
            final_text = ev["text"]
        elif ev["type"] == "error":
            # stream_chat 自身不發 error（它的工具失敗是 is_error tool_result，會續跑）；
            # 這條是防呆——真有 error frame 就讓呼叫端知道，而非把空字串當成功回覆。
            raise RuntimeError(ev["message"])
    return final_text
