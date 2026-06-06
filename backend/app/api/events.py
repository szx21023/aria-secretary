from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.event import Event
from app.schemas.event import EventRead

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("", response_model=list[EventRead])
async def list_events(
    db: AsyncSession = Depends(get_db),
    start: datetime | None = Query(None, description="只取 start_at >= 此時間"),
    end: datetime | None = Query(None, description="只取 start_at < 此時間"),
) -> list[Event]:
    stmt = select(Event).order_by(Event.start_at)
    if start is not None:
        stmt = stmt.where(Event.start_at >= start)
    if end is not None:
        stmt = stmt.where(Event.start_at < end)
    result = await db.scalars(stmt)
    return list(result)
