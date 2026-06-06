from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.event import Event
from app.schemas.event import EventCreate, EventRead, EventUpdate

router = APIRouter(prefix="/api/events", tags=["events"])


async def _get_or_404(db: AsyncSession, event_id: str) -> Event:
    event = await db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到該行程")
    return event


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


@router.post("", response_model=EventRead, status_code=status.HTTP_201_CREATED)
async def create_event(payload: EventCreate, db: AsyncSession = Depends(get_db)) -> Event:
    event = Event(**payload.model_dump())
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


@router.get("/{event_id}", response_model=EventRead)
async def get_event(event_id: str, db: AsyncSession = Depends(get_db)) -> Event:
    return await _get_or_404(db, event_id)


@router.patch("/{event_id}", response_model=EventRead)
async def update_event(
    event_id: str, payload: EventUpdate, db: AsyncSession = Depends(get_db)
) -> Event:
    event = await _get_or_404(db, event_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(event, field, value)
    if event.end_at <= event.start_at:
        raise HTTPException(status_code=422, detail="end_at 必須晚於 start_at")
    await db.commit()
    await db.refresh(event)
    return event


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(event_id: str, db: AsyncSession = Depends(get_db)) -> None:
    event = await _get_or_404(db, event_id)
    await db.delete(event)
    await db.commit()
