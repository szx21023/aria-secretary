from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.helpers import reject_null_fields
from app.common.exceptions import NotFoundException
from app.db import get_db
from app.models.event import Event
from app.schemas.event import EventCreate, EventRead, EventUpdate
from app.services.scheduling import INTERVAL_ERROR, interval_ok

router = APIRouter(prefix="/api/events", tags=["events"])

# Event 的 NOT NULL 欄位，部分更新時不可被顯式設成 null
_REQUIRED_FIELDS = frozenset({"title", "start_at", "end_at", "category", "status", "is_milestone"})


async def _get_or_404(db: AsyncSession, event_id: str) -> Event:
    event = await db.get(Event, event_id)
    if event is None:
        raise NotFoundException("找不到該行程")
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
async def update_event(event_id: str, payload: EventUpdate, db: AsyncSession = Depends(get_db)) -> Event:
    event = await _get_or_404(db, event_id)
    changes = payload.model_dump(exclude_unset=True)
    reject_null_fields(changes, _REQUIRED_FIELDS)

    # 跨欄位規則只能在「合併進現有行程後」才驗證得了：部分更新可能只送了
    # start_at 或 end_at 其中一個，得跟資料庫裡的另一半比對。null 已被
    # reject_null_fields 擋掉，所以這裡 new_start / new_end 必為非 None。
    new_start = changes.get("start_at", event.start_at)
    new_end = changes.get("end_at", event.end_at)
    if not interval_ok(new_start, new_end):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=INTERVAL_ERROR)

    for field, value in changes.items():
        setattr(event, field, value)
    await db.commit()
    await db.refresh(event)
    return event


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(event_id: str, db: AsyncSession = Depends(get_db)) -> None:
    event = await _get_or_404(db, event_id)
    await db.delete(event)
    await db.commit()
