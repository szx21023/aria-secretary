from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import ReminderKind


class ReminderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    subtitle: str | None = None
    trigger_at: datetime | None = None
    recurrence: str | None = None
    kind: ReminderKind
    enabled: bool
