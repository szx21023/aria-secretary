"""Alembic migration：upgrade head 對全新 DB 建出完整 schema，且可重複執行（idempotent）。

取代了舊的手刻 _add_missing_columns。平時測試的 in-memory 庫走 Base.metadata.create_all，
這裡才實際走 Alembic 路徑（也是正式啟動 init_db 走的路徑）。
"""

import sqlite3

from app.config import get_settings
from app.db import _upgrade_to_head


def _tables(path: str) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def _columns(path: str, table: str) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def test_upgrade_head_builds_schema_and_is_idempotent(tmp_path, monkeypatch):
    db = tmp_path / "migrate.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db}")
    get_settings.cache_clear()  # 讓 env.py 取到 temp DB
    try:
        _upgrade_to_head()
        _upgrade_to_head()  # 已在 head → no-op，不可重跑就報錯
    finally:
        get_settings.cache_clear()

    tables = _tables(str(db))
    assert {"conversations", "events", "reminders", "tasks", "messages"} <= tables
    assert "alembic_version" in tables  # 版本表落地

    # 先前手刻補的欄位，baseline 也要建出來
    assert "fired_at" in _columns(str(db), "reminders")
    assert "notified_at" in _columns(str(db), "events")
    assert "line_user_id" in _columns(str(db), "conversations")
