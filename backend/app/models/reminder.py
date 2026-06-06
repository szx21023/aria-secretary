from datetime import datetime

from sqlalchemy import Boolean, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UTCDateTime, UUIDMixin
from app.models.enums import ReminderKind


class Reminder(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "reminders"

    title: Mapped[str] = mapped_column(String(200))
    subtitle: Mapped[str | None] = mapped_column(String(200), nullable=True)
    trigger_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    recurrence: Mapped[str | None] = mapped_column(String(100), nullable=True)
    kind: Mapped[ReminderKind] = mapped_column(SAEnum(ReminderKind), default=ReminderKind.meeting)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
