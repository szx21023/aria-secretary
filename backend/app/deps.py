"""FastAPI 共用依賴 — DB session 別名與分頁參數。"""

from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db

# 端點簽名用 `db: DbSession` 取代 `db: AsyncSession = Depends(get_db)`
DbSession = Annotated[AsyncSession, Depends(get_db)]


class Pagination:
    """通用分頁 ?page=1&size=20；offset 給 SQL OFFSET 用。"""

    def __init__(
        self,
        page: Annotated[int, Query(ge=1)] = 1,
        size: Annotated[int, Query(ge=1, le=200)] = 20,
    ) -> None:
        self.page = page
        self.size = size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


PageParams = Annotated[Pagination, Depends()]
