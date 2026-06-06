import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, TypeDecorator
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """確保進出 DB 的 datetime 一律是 UTC aware。

    SQLite 會把 datetime 存成 naive 字串，讀回來不帶時區資訊，
    前端就無從得知是哪個時區。這裡綁定時轉成 UTC、讀取時補上 UTC tzinfo，
    讓 API 永遠輸出帶 offset 的 ISO 字串。
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    pass


class UUIDMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now, onupdate=_now)
