import asyncio
import logging
from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

logger = logging.getLogger(__name__)

# backend/ 目錄（alembic/ 與 alembic.ini 所在）；用絕對路徑，才不依賴啟動時的 cwd。
_BACKEND_DIR = Path(__file__).resolve().parent.parent

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


def _alembic_config():
    """以絕對路徑指向 alembic/，sqlalchemy.url 由 env.py 從 settings 取得。"""
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    return cfg


def _upgrade_to_head() -> None:
    from alembic import command

    command.upgrade(_alembic_config(), "head")


async def init_db() -> None:
    """套用 Alembic migration 到最新版（含建表）。

    Alembic 走同步，包進 to_thread 不卡事件迴圈。schema 變更一律新增 migration，
    不再手刻 ALTER（取代了舊的 _add_missing_columns）。
    注意：測試各自用 Base.metadata.create_all 建表，不經過這裡。
    """
    await asyncio.to_thread(_upgrade_to_head)
