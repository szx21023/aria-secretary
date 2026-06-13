import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

engine = create_async_engine(settings.database_url, echo=False, future=True)

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency：每個 request 一個 session。

    端點裡的例外（含 commit 失敗）往上拋時，明確 rollback 再 re-raise，
    避免 session 帶著未結束的交易回到連線池。
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


# 後來加上的欄位 → SQLite ALTER 子句。create_all 只建缺的「表」，不會替既有表補「欄位」，
# 所以舊 aria.db 升級時要靠這裡逐欄補上。schema 穩定後改 Alembic 一次取代這段。
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "conversations": {"line_user_id": "VARCHAR(64)"},
    "reminders": {"fired_at": "DATETIME"},
    "events": {"notified_at": "DATETIME"},
}


async def _add_missing_columns(conn) -> None:
    """對既有 SQLite 庫補上 _ADDED_COLUMNS 裡缺的欄位（皆 nullable，免回填）。"""
    for table, columns in _ADDED_COLUMNS.items():
        rows = await conn.exec_driver_sql(f"PRAGMA table_info({table})")
        existing = {r[1] for r in rows.fetchall()}
        for col, ddl_type in columns.items():
            if col not in existing:
                await conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {col} {ddl_type}")
                logger.info("migration: %s.%s 已補上", table, col)


async def init_db() -> None:
    """建立資料表。M0 用 create_all；schema 穩定後改 Alembic。"""
    # 確保所有 model 都被 import 進 metadata
    from app import models  # noqa: F401
    from app.models.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _add_missing_columns(conn)
