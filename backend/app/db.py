from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, echo=False, future=True)

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency：每個 request 一個 session。"""
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    """建立資料表。M0 用 create_all；schema 穩定後改 Alembic。"""
    # 確保所有 model 都被 import 進 metadata
    from app import models  # noqa: F401
    from app.models.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
