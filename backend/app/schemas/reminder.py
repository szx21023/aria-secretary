from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import ReminderKind
from app.schemas.types import UTCDatetime


class ReminderReadSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    subtitle: str | None = None
    trigger_at: datetime | None = None
    recurrence: str | None = None
    kind: ReminderKind
    is_enabled: bool


class ReminderCreateSchema(BaseModel):
    title: str
    subtitle: str | None = None
    trigger_at: UTCDatetime | None = None
    recurrence: str | None = None
    kind: ReminderKind = ReminderKind.meeting
    is_enabled: bool = True


class ReminderUpdateSchema(BaseModel):
    """部分更新：只送要改的欄位。"""

    title: str | None = None
    subtitle: str | None = None
    trigger_at: UTCDatetime | None = None
    recurrence: str | None = None
    kind: ReminderKind | None = None
    is_enabled: bool | None = None
