from datetime import datetime

from sqlalchemy import Boolean, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UTCDateTime, UUIDMixin
from app.models.enums import TaskPriority


class Task(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tasks"

    title: Mapped[str] = mapped_column(String(200))
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    priority: Mapped[TaskPriority | None] = mapped_column(SAEnum(TaskPriority), nullable=True)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
