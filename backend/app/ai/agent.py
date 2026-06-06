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


async def stream_chat(
    db: AsyncSession, history: list[dict], user_text: str
) -> AsyncGenerator[ChatEvent, None]:
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
                yield {"type": "tool", "name": block.name}
                # 工具執行失敗（DB 錯誤、未預期例外）回成 is_error 的 tool_result，
                # 讓模型知道失敗並自我修正，而不是讓整輪對話死在 broad except。
                try:
                    content = await run_tool(db, block.name, block.input or {})
                    tr = {"type": "tool_result", "tool_use_id": block.id, "content": content}
                except Exception as e:
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
    if hit_cap and not text:
        # 工具輪數用盡且沒生出任何文字 → 別吐空泡泡，給可重試的提示
        logger.warning("tool round cap (%d) 用盡仍無最終回覆", MAX_TOOL_ROUNDS)
        text = "這次的查詢有點複雜，我沒能整理出完整回覆，可以換個方式再問一次嗎？"
    yield {"type": "done", "text": text}
