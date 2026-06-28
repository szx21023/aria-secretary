import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, String, TypeDecorator
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    """確保進出 DB 的 datetime 一律是 UTC aware。

    SQLite 會把 datetime 存成 naive 字串，讀回來不帶時區資訊，
    前端就無從得知是哪個時區。這裡綁定時一律轉成 naive-UTC 存入、讀取時補上 UTC tzinfo，
    讓 API 永遠輸出帶 offset 的 ISO 字串。

    底層欄位是 TIMESTAMP WITHOUT TIME ZONE（Postgres）：綁定時必須去掉 tzinfo，
    否則 asyncpg 會拒收 aware datetime（can't bind aware value to naive column）。
    SQLite 不檢查時區，但同樣存 naive-UTC 保持一致。
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class Base(DeclarativeBase):
    pass


class UUIDMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now, onupdate=_now)
