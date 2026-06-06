from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.helpers import reject_null_fields
from app.db import get_db
from app.models.task import Task
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

# Task 的 NOT NULL 欄位，部分更新時不可被顯式設成 null
_REQUIRED_FIELDS = frozenset({"title", "done"})


async def _get_or_404(db: AsyncSession, task_id: str) -> Task:
    task = await db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到該待辦")
    return task


@router.get("", response_model=list[TaskRead])
async def list_tasks(db: AsyncSession = Depends(get_db)) -> list[Task]:
    result = await db.scalars(
        select(Task).order_by(Task.done, Task.due_at.is_(None), Task.due_at)
    )
    return list(result)


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(payload: TaskCreate, db: AsyncSession = Depends(get_db)) -> Task:
    task = Task(**payload.model_dump())
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(task_id: str, db: AsyncSession = Depends(get_db)) -> Task:
    return await _get_or_404(db, task_id)


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: str, payload: TaskUpdate, db: AsyncSession = Depends(get_db)
) -> Task:
    task = await _get_or_404(db, task_id)
    changes = payload.model_dump(exclude_unset=True)
    reject_null_fields(changes, _REQUIRED_FIELDS)
    for field, value in changes.items():
        setattr(task, field, value)
    await db.commit()
    await db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: str, db: AsyncSession = Depends(get_db)) -> None:
    task = await _get_or_404(db, task_id)
    await db.delete(task)
    await db.commit()
