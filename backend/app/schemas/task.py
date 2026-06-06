from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import TaskPriority


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    due_at: datetime | None = None
    priority: TaskPriority | None = None
    done: bool
