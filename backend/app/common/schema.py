"""跨模組共用 schema — 分頁容器、ORM 轉 Pydantic 基底。"""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """泛型分頁回應；`total` 是過濾後總筆數，`has_more` 供 infinite scroll。"""

    data: list[T]
    page: int
    size: int
    total: int
    has_more: bool


class OrmModel(BaseModel):
    """讓 Pydantic 直接從 SQLAlchemy ORM 物件驗證欄位。"""

    model_config = ConfigDict(from_attributes=True)
