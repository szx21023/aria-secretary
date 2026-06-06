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


class TaskCreate(BaseModel):
    title: str
    due_at: datetime | None = None
    priority: TaskPriority | None = None
    done: bool = False


class TaskUpdate(BaseModel):
    """部分更新：只送要改的欄位。"""

    title: str | None = None
    due_at: datetime | None = None
    priority: TaskPriority | None = None
    done: bool | None = None
