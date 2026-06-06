"""串流式 agentic loop：手動處理 tool-use 迴圈，逐字串流回前端。

採手動 loop（非 SDK tool_runner）以便：逐 token 串流、攔每個 tool call 推 SSE、之後加權限控制。
"""

from collections.abc import AsyncGenerator
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import MODEL, get_client
from app.ai.executor import run_tool
from app.ai.system_prompt import SYSTEM_PROMPT
from app.ai.tools import TOOLS
from app.config import get_settings

_TZ = ZoneInfo(get_settings().app_tz)
MAX_TOOL_ROUNDS = 5


def _now_context() -> str:
    now = datetime.now(_TZ)
    week = "一二三四五六日"[now.weekday()]
    return f"（目前時間：{now.strftime('%Y-%m-%d %H:%M')} 星期{week}）"


async def stream_chat(
    db: AsyncSession, history: list[dict], user_text: str
) -> AsyncGenerator[dict, None]:
    """逐步 yield 事件 dict：

    - {"type": "delta", "text": ...}  秘書回覆的文字片段
    - {"type": "tool",  "name": ...}  正在呼叫某工具
    - {"type": "done",  "text": ...}  完成，附完整回覆（供持久化）
    """
    client = get_client()
    # 動態情境（現在時間）走 message 層，不污染 system，保住 prompt cache
    messages: list[dict] = [
        *history,
        {"role": "user", "content": f"{_now_context()}\n{user_text}"},
    ]
    full_text = ""

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
            break

        # 保留整段 assistant content（含 thinking 與 tool_use），執行工具後回灌
        messages.append({"role": "assistant", "content": final.content})
        tool_results = []
        for block in final.content:
            if block.type == "tool_use":
                yield {"type": "tool", "name": block.name}
                result = await run_tool(db, block.name, block.input or {})
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": result}
                )
        messages.append({"role": "user", "content": tool_results})

    yield {"type": "done", "text": full_text.strip()}
