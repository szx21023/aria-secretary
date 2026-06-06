from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.reminder import Reminder
from app.schemas.reminder import ReminderRead

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


@router.get("", response_model=list[ReminderRead])
async def list_reminders(db: AsyncSession = Depends(get_db)) -> list[Reminder]:
    result = await db.scalars(
        select(Reminder).order_by(Reminder.enabled.desc(), Reminder.trigger_at)
    )
    return list(result)
