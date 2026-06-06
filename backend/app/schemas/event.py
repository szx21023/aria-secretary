from datetime import datetime

from pydantic import BaseModel, ConfigDict

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
