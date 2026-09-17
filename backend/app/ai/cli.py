"""獨立命令列 REPL：直接驅動 app.ai.agent 的同一顆 agent loop（與網頁／LINE 共用）。

用途是本機測試／debug agent 與工具呼叫，故對話記憶「不落地」——history 只活在本行程的
記憶體，結束即消失，不寫入 Message 資料表（與 services/conversation 的持久化路徑刻意分開）。
工具對 events/tasks/reminders 的實際增刪改仍會寫進 DATABASE_URL 指向的資料庫——那是 agent
的本職，無法也不該繞開；要隔離就用另一個 DATABASE_URL（例如指向拋棄式 SQLite 檔）。

這裡用 print 而非 logging：REPL 的 stdout 就是它的產品輸出（UI），不是應用內部診斷訊息，
不適用「禁止 print」那條（那針對的是 app/service 層以 print 充當 log 的情況）。

跑法（在 backend/ 下，需已在 .env 設好 ANTHROPIC_API_KEY）：
    .venv/bin/python -m app.ai.cli
指令：/reset 清空本次記憶、/exit（或 Ctrl-D）離開。
"""

import asyncio
import logging
import sys

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agent import stream_chat
from app.config import get_settings
from app.db import AsyncSessionLocal, init_db
from app.models.enums import MessageRole
from app.seed import seed_if_empty

logger = logging.getLogger(__name__)
_USER_PROMPT = "你 > "


async def _one_turn(db: AsyncSession, history: list[dict], user_text: str) -> str:
    """跑一輪 agent loop：逐字印出回覆、標示每個工具呼叫與資料變更，回傳最終文字。"""
    at_line_start = True
    streamed_any = False
    final_text = ""

    sys.stdout.write("Aria > ")
    sys.stdout.flush()
    async for event in stream_chat(db, history, user_text):
        kind = event["type"]
        if kind == "delta":
            sys.stdout.write(event["text"])
            sys.stdout.flush()
            streamed_any = True
            at_line_start = event["text"].endswith("\n")
        elif kind == "tool":
            if not at_line_start:
                print()
            print(f"  🔧 呼叫工具：{event['name']}")
            at_line_start = True
        elif kind == "state_changed":
            if not at_line_start:
                print()
            print(f"  ✎ 已變更：{event['resource']}")
            at_line_start = True
        elif kind == "done":
            final_text = event["text"]

    # 用盡輪數時的 fallback 文字不經 delta 事件；整輪若一個字都沒串過就補印一次，別讓畫面空白
    if not streamed_any and final_text:
        sys.stdout.write(final_text)
        at_line_start = final_text.endswith("\n")
    if not at_line_start:
        print()
    return final_text


async def _repl() -> None:
    settings = get_settings()
    if not settings.anthropic_api_key:
        # 本專案沒有離線降級，缺金鑰時 agent 會在第一次呼叫 API 就爆；先講清楚免得看到晦澀 traceback
        print("⚠️  未設定 ANTHROPIC_API_KEY，agent 無法呼叫 Claude。請先在 backend/.env 設定後再跑。")
        return

    # httpx 每次請求會 INFO 一行；REPL 未配置 logging，壓掉以免日後有人開 log 時洗版對話畫面
    logging.getLogger("httpx").setLevel(logging.WARNING)

    await init_db()  # 確保資料表存在（工具要查 events/tasks/reminders）
    async with AsyncSessionLocal() as db:
        if settings.seed_on_empty:
            await seed_if_empty(db)  # 空庫時鋪範例資料，才有東西可問可改（idempotent）

        history: list[dict] = []  # 臨時記憶：只活在本行程，結束即丟，不寫入 Message 表
        print("Aria CLI（獨立臨時記憶）。直接輸入訊息開始對話；/reset 清空、/exit 離開。\n")

        while True:
            try:
                user_text = (await asyncio.to_thread(input, _USER_PROMPT)).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not user_text:
                continue
            if user_text in ("/exit", "/quit"):
                break
            if user_text == "/reset":
                history.clear()
                print("（已清空本次對話記憶）\n")
                continue

            try:
                reply = await _one_turn(db, history, user_text)
            except Exception as e:  # noqa: BLE001 — debug REPL：任一輪出錯都印出來但保住 session，別讓整段對話陪葬
                print(f"\n⚠️  這輪出錯，已跳過（記憶未更新）：{e}")
                # 中途可能留下未收尾的交易，rollback 讓下一輪的工具與查詢仍在乾淨 session 上跑
                try:
                    await db.rollback()
                except Exception:
                    logger.exception("錯誤後 rollback 也失敗")
                continue
            # 只把純文字回灌臨時記憶，對齊網頁／LINE 的持久化格式（不留 thinking／tool_use 區塊）；
            # role 用 MessageRole.value，與 services.load_history 產出的 dict 逐字一致
            history.append({"role": MessageRole.user.value, "content": user_text})
            history.append({"role": MessageRole.assistant.value, "content": reply})
            print()

    print("bye 👋")


if __name__ == "__main__":
    asyncio.run(_repl())
