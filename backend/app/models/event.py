from datetime import datetime

from sqlalchemy import Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UTCDateTime, UUIDMixin
from app.models.enums import EventCategory, EventStatus


class Event(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "events"

    title: Mapped[str] = mapped_column(String(200))
    start_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    end_at: Mapped[datetime] = mapped_column(UTCDateTime)
    category: Mapped[EventCategory] = mapped_column(
        SAEnum(EventCategory), default=EventCategory.meeting
    )
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    attendees: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[EventStatus] = mapped_column(
        SAEnum(EventStatus), default=EventStatus.scheduled
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 「即將開始」推播已送出的時間戳；非 None 代表已推過，排程器不再重推。
    notified_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
