"""db._add_missing_columns：對既有 SQLite 庫補上後來新增的欄位，且可重複執行不報錯。

這條只在「升級既有 aria.db」時才跑（create_all 只建缺的表、不補欄位），平時測試的 in-memory
庫都是 create_all 全新建出來、本來就有欄位，所以這個 migration 路徑唯有在這裡才被實際走到。
"""

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.db import _add_missing_columns

pytestmark = pytest.mark.asyncio


async def _columns(conn, table: str) -> set[str]:
    rows = await conn.exec_driver_sql(f"PRAGMA table_info({table})")
    return {r[1] for r in rows.fetchall()}


async def test_adds_missing_columns_and_is_idempotent():
    engine = create_async_engine("sqlite+aiosqlite://")
    try:
        async with engine.begin() as conn:
            # 模擬「新欄位出現前」的舊 schema
            await conn.exec_driver_sql("CREATE TABLE reminders (id TEXT PRIMARY KEY, title TEXT)")
            await conn.exec_driver_sql("CREATE TABLE conversations (id TEXT PRIMARY KEY, title TEXT)")
            await conn.exec_driver_sql("CREATE TABLE events (id TEXT PRIMARY KEY, title TEXT)")

            await _add_missing_columns(conn)

            assert "fired_at" in await _columns(conn, "reminders")
            assert "line_user_id" in await _columns(conn, "conversations")
            assert "notified_at" in await _columns(conn, "events")

            # 再跑一次：欄位已存在 → no-op，不可重複 ALTER 而拋錯
            await _add_missing_columns(conn)
    finally:
        await engine.dispose()


async def test_existing_column_is_left_untouched():
    # 欄位已經在的表不該被再 ALTER（會 "duplicate column" 報錯）
    engine = create_async_engine("sqlite+aiosqlite://")
    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql(
                "CREATE TABLE reminders (id TEXT PRIMARY KEY, title TEXT, fired_at DATETIME)"
            )
            await conn.exec_driver_sql("CREATE TABLE conversations (id TEXT PRIMARY KEY)")
            await conn.exec_driver_sql("CREATE TABLE events (id TEXT PRIMARY KEY)")

            await _add_missing_columns(conn)  # 不應拋錯

            assert "fired_at" in await _columns(conn, "reminders")
    finally:
        await engine.dispose()
