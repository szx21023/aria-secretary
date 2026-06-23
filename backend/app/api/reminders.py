from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.helpers import reject_null_fields
from app.common.exceptions import NotFoundException
from app.db import get_db
from app.models.reminder import Reminder
from app.schemas.reminder import ReminderCreate, ReminderRead, ReminderUpdate

router = APIRouter(prefix="/api/reminders", tags=["reminders"])

# Reminder 的 NOT NULL 欄位，部分更新時不可被顯式設成 null
_REQUIRED_FIELDS = frozenset({"title", "kind", "enabled"})


async def _get_or_404(db: AsyncSession, reminder_id: str) -> Reminder:
    reminder = await db.get(Reminder, reminder_id)
    if reminder is None:
        raise NotFoundException("找不到該提醒")
    return reminder


@router.get("", response_model=list[ReminderRead])
async def list_reminders(db: AsyncSession = Depends(get_db)) -> list[Reminder]:
    result = await db.scalars(select(Reminder).order_by(Reminder.enabled.desc(), Reminder.trigger_at))
    return list(result)


@router.post("", response_model=ReminderRead, status_code=status.HTTP_201_CREATED)
async def create_reminder(payload: ReminderCreate, db: AsyncSession = Depends(get_db)) -> Reminder:
    reminder = Reminder(**payload.model_dump())
    db.add(reminder)
    await db.commit()
    await db.refresh(reminder)
    return reminder


@router.get("/{reminder_id}", response_model=ReminderRead)
async def get_reminder(reminder_id: str, db: AsyncSession = Depends(get_db)) -> Reminder:
    return await _get_or_404(db, reminder_id)


@router.patch("/{reminder_id}", response_model=ReminderRead)
async def update_reminder(reminder_id: str, payload: ReminderUpdate, db: AsyncSession = Depends(get_db)) -> Reminder:
    reminder = await _get_or_404(db, reminder_id)
    changes = payload.model_dump(exclude_unset=True)
    reject_null_fields(changes, _REQUIRED_FIELDS)
    for field, value in changes.items():
        setattr(reminder, field, value)
    await db.commit()
    await db.refresh(reminder)
    return reminder


@router.delete("/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reminder(reminder_id: str, db: AsyncSession = Depends(get_db)) -> None:
    reminder = await _get_or_404(db, reminder_id)
    await db.delete(reminder)
    await db.commit()
