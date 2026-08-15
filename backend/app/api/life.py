from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas.life import LifeProfileWrite, LifeRead
from app.services import life as life_service

router = APIRouter(prefix="/api/life", tags=["life"])


@router.get("", response_model=LifeRead)
async def get_life(db: AsyncSession = Depends(get_db)) -> LifeRead:
    """尚未設定過生日時回 birthday=null、stats=null（不是 404）——前端據此顯示設定表單。

    里程碑（標為 is_milestone 的未來行程）不受此影響，一律附上。
    """
    return await life_service.build_read(db)


@router.put("", response_model=LifeRead)
async def put_life(payload: LifeProfileWrite, db: AsyncSession = Depends(get_db)) -> LifeRead:
    """設定／更新基準資料。單列 upsert，重複呼叫不會累積多筆。"""
    if payload.birthday > life_service.today_local():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="生日不能是未來的日期",
        )
    await life_service.upsert_profile(db, payload.birthday, payload.life_expectancy)
    return await life_service.build_read(db)
