"""人生倒數：日期推導與 profile 讀寫。

所有數字都以「app 時區的今天」為基準（不是 UTC 今天），跨午夜才會變動。
「剩餘」一律定義為 `(終點 - 今天).days`，不含今天——因此恆有
`lived_days + remaining_days == total_days`；終點當天顯示 0。
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.event import Event
from app.models.life import LifeProfile
from app.schemas.life import LifeRead, LifeStats, MilestoneRead

_TZ = ZoneInfo(get_settings().app_tz)

# 頁面一次最多列這麼多個未來里程碑，避免標記過多時整頁被灌爆。
MILESTONE_LIMIT = 20


def today_local() -> date:
    return datetime.now(_TZ).date()


def add_years(d: date, years: int) -> date:
    """d 加上整數年；2/29 落在非閏年時退回 2/28。"""
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)


def full_years_between(start: date, end: date) -> int:
    """start 到 end 之間的完整年數（未滿一年不計）；end 早於 start 回 0。"""
    if end <= start:
        return 0
    years = end.year - start.year
    if (end.month, end.day) < (start.month, start.day):
        years -= 1
    return years


def _last_day_of_month(d: date) -> date:
    first_next = date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)
    return first_next - timedelta(days=1)


def _next_birthday(birthday: date, today: date) -> date:
    """今天就是生日時回今天（距離 0 天）。"""
    candidate = add_years(birthday, today.year - birthday.year)
    if candidate < today:
        candidate = add_years(birthday, today.year - birthday.year + 1)
    return candidate


def compute_stats(birthday: date, life_expectancy: int, today: date | None = None) -> LifeStats:
    """由生日與預期壽命推導倒數數字。今天早於生日（未出生）時已過部分視為 0。"""
    today = today or today_local()
    end_date = add_years(birthday, life_expectancy)

    total_days = (end_date - birthday).days
    lived_days = max(0, (today - birthday).days)
    remaining_days = max(0, (end_date - today).days)
    # total_days 恆 > 0（life_expectancy 最小為 1），除法安全；活過終點則封頂 100%
    percent_lived = min(100.0, round(lived_days / total_days * 100, 1))

    return LifeStats(
        today=today,
        end_date=end_date,
        age=full_years_between(birthday, today),
        total_days=total_days,
        lived_days=lived_days,
        remaining_days=remaining_days,
        percent_lived=percent_lived,
        lived_weeks=lived_days // 7,
        remaining_weeks=remaining_days // 7,
        remaining_years=full_years_between(today, end_date),
        days_left_this_year=(date(today.year, 12, 31) - today).days,
        days_left_this_month=(_last_day_of_month(today) - today).days,
        next_birthday_in_days=(_next_birthday(birthday, today) - today).days,
    )


def local_date(dt: datetime) -> date:
    """UTC aware datetime → app 時區的日期。"""
    return dt.astimezone(_TZ).date()


def to_milestone(event: Event, today: date, birthday: date | None) -> MilestoneRead:
    """進度以「這筆行程被建立的那天」為起點：分母＝目標日−建立日，分子＝今天−建立日。

    起點是 events.created_at，不是「被標成里程碑的那天」——把一筆早就存在的舊行程
    標成里程碑時，進度會一開始就顯示走了一大半。這是刻意的取捨（不為此多存一個時間戳）。

    建立日晚於目標日（例如補記一個近在眼前的目標）會讓分母 <= 0，此時視為已走完 100%，
    不讓比例變成負數或除以零。
    """
    target = local_date(event.start_at)
    created = local_date(event.created_at)
    total_days = (target - created).days
    elapsed_days = max(0, min((today - created).days, total_days))
    percent_elapsed = 100.0 if total_days <= 0 else round(elapsed_days / total_days * 100, 1)

    return MilestoneRead(
        id=event.id,
        title=event.title,
        start_at=event.start_at,
        target_date=target,
        days_left=(target - today).days,
        created_date=created,
        total_days=total_days,
        elapsed_days=elapsed_days,
        percent_elapsed=percent_elapsed,
        age_at=full_years_between(birthday, target) if birthday else None,
        category=event.category,
        location=event.location,
        note=event.note,
    )


async def list_milestones(db: AsyncSession, birthday: date | None = None) -> list[MilestoneRead]:
    """今天（含）之後、標為里程碑的行程，由近到遠。

    以「在地日期」而非時間戳篩選：今天稍早的里程碑仍該整天看得見（剩 0 天），
    不該在時間一過就從頁面上消失。
    """
    today = today_local()
    # 邊界放寬一天再於 Python 端用在地日期精確篩，免得 UTC/在地日界差把當天的漏掉
    cutoff = datetime.combine(today, time.min, tzinfo=_TZ) - timedelta(days=1)
    rows = await db.scalars(select(Event).where(Event.is_milestone, Event.start_at >= cutoff).order_by(Event.start_at))
    upcoming = [e for e in rows if local_date(e.start_at) >= today]
    return [to_milestone(e, today, birthday) for e in upcoming[:MILESTONE_LIMIT]]


async def build_read(db: AsyncSession) -> LifeRead:
    """人生頁的完整資料：基準、倒數數字、未來里程碑。"""
    profile = await get_profile(db)
    birthday = profile.birthday if profile else None
    milestones = await list_milestones(db, birthday)
    if profile is None:
        return LifeRead(milestones=milestones)
    return LifeRead(
        birthday=profile.birthday,
        life_expectancy=profile.life_expectancy,
        stats=compute_stats(profile.birthday, profile.life_expectancy),
        milestones=milestones,
    )


async def get_profile(db: AsyncSession) -> LifeProfile | None:
    """取那唯一一列；沒設定過回 None。"""
    return await db.scalar(select(LifeProfile).order_by(LifeProfile.created_at).limit(1))


async def upsert_profile(db: AsyncSession, birthday: date, life_expectancy: int) -> LifeProfile:
    """有就更新、沒有才新增，維持全表單列。"""
    profile = await get_profile(db)
    if profile is None:
        profile = LifeProfile(birthday=birthday, life_expectancy=life_expectancy)
        db.add(profile)
    else:
        profile.birthday = birthday
        profile.life_expectancy = life_expectancy
    await db.commit()
    await db.refresh(profile)
    return profile
