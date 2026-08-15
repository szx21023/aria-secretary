from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from app.models.enums import EventCategory, EventStatus
from app.schemas.types import UTCDatetime
from app.services.scheduling import INTERVAL_ERROR, interval_ok


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
    is_milestone: bool = False


class EventCreate(BaseModel):
    title: str
    start_at: UTCDatetime
    end_at: UTCDatetime
    category: EventCategory = EventCategory.meeting
    location: str | None = None
    attendees: int | None = None
    status: EventStatus = EventStatus.scheduled
    note: str | None = None
    is_milestone: bool = False

    @model_validator(mode="after")
    def _end_after_start(self) -> "EventCreate":
        if not interval_ok(self.start_at, self.end_at):
            raise ValueError(INTERVAL_ERROR)
        return self


class EventUpdate(BaseModel):
    """部分更新：只送要改的欄位。

    start_at / end_at 的「end 必須晚於 start」是跨欄位規則，無法在這個
    可只送一個欄位的部分更新模型內檢查；改由 router 合併進現有行程後再驗證。
    """

    title: str | None = None
    start_at: UTCDatetime | None = None
    end_at: UTCDatetime | None = None
    category: EventCategory | None = None
    location: str | None = None
    attendees: int | None = None
    status: EventStatus | None = None
    note: str | None = None
    is_milestone: bool | None = None
