from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from app.models.enums import EventCategory, EventStatus


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    start_at: datetime
    end_at: datetime
    category: EventCategory
    location: str | None = None
    attendees: int | None = None
    status: EventStatus
    note: str | None = None


class EventCreate(BaseModel):
    title: str
    start_at: datetime
    end_at: datetime
    category: EventCategory = EventCategory.meeting
    location: str | None = None
    attendees: int | None = None
    status: EventStatus = EventStatus.scheduled
    note: str | None = None

    @model_validator(mode="after")
    def _end_after_start(self) -> "EventCreate":
        if self.end_at <= self.start_at:
            raise ValueError("end_at 必須晚於 start_at")
        return self


class EventUpdate(BaseModel):
    """部分更新：只送要改的欄位。"""

    title: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    category: EventCategory | None = None
    location: str | None = None
    attendees: int | None = None
    status: EventStatus | None = None
    note: str | None = None
