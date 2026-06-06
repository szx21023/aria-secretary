from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.task import Task
from app.schemas.task import TaskRead

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskRead])
async def list_tasks(db: AsyncSession = Depends(get_db)) -> list[Task]:
    result = await db.scalars(
        select(Task).order_by(Task.done, Task.due_at.is_(None), Task.due_at)
    )
    return list(result)
