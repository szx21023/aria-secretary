"""把 Claude 的 tool 呼叫對應到 DB 查詢，回傳給模型閱讀的文字結果。

M3 只有唯讀工具（get_schedule / find_free_slots）。寫入工具留待 M4。
"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.event import Event
from app.services.scheduling import find_free_slots

_TZ = ZoneInfo(get_settings().app_tz)

# 找空檔的工作時間窗（在地時間）
WORK_START = time(9, 0)
WORK_END = time(18, 0)


def _now_local() -> datetime:
    return datetime.now(_TZ)


def _parse_date(s: str | None) -> date:
    if not s:
        return _now_local().date()
    return date.fromisoformat(s)


def _local_day_bounds(d: date) -> tuple[datetime, datetime]:
    """回傳該在地日期的 [00:00, 隔日00:00) 對應的 UTC datetime。"""
    start = datetime.combine(d, time.min, tzinfo=_TZ).astimezone(timezone.utc)
    end = datetime.combine(d + timedelta(days=1), time.min, tzinfo=_TZ).astimezone(timezone.utc)
    return start, end


def _fmt(dt: datetime) -> str:
    return dt.astimezone(_TZ).strftime("%H:%M")


def _derive_status(ev: Event, now: datetime) -> str:
    if now >= ev.end_at:
        return "已結束"
    if now >= ev.start_at:
        return "進行中"
    return "未開始"


async def _events_between(db: AsyncSession, start: datetime, end: datetime) -> list[Event]:
    result = await db.scalars(
        select(Event).where(Event.start_at >= start, Event.start_at < end).order_by(Event.start_at)
    )
    return list(result)


async def get_schedule(db: AsyncSession, date: str | None = None, range: str = "day") -> str:
    try:
        d = _parse_date(date)
    except ValueError:
        return f"日期格式無法解析：{date!r}，請用 YYYY-MM-DD，或省略代表今天。"
    now = _now_local().astimezone(timezone.utc)
    if range == "week":
        # 該日所在週的週一～週日
        monday = d - timedelta(days=d.weekday())
        start, _ = _local_day_bounds(monday)
        _, end = _local_day_bounds(monday + timedelta(days=6))
        label = f"{monday.isoformat()} 那一週"
    else:
        start, end = _local_day_bounds(d)
        label = d.isoformat()

    events = await _events_between(db, start, end)
    if not events:
        return f"{label} 沒有任何行程。"

    lines = [f"{label} 共 {len(events)} 個行程："]
    for e in events:
        loc = f"，地點：{e.location}" if e.location else ""
        ppl = f"，{e.attendees} 人" if e.attendees else ""
        when = f"{e.start_at.astimezone(_TZ).strftime('%m/%d %H:%M')}–{_fmt(e.end_at)}"
        lines.append(
            f"- {when} {e.title}（{e.category.value}，{_derive_status(e, now)}{loc}{ppl}）"
        )
    return "\n".join(lines)


async def find_free_slots_tool(
    db: AsyncSession, date: str | None = None, min_minutes: int = 30
) -> str:
    try:
        d = _parse_date(date)
    except ValueError:
        return f"日期格式無法解析：{date!r}，請用 YYYY-MM-DD，或省略代表今天。"
    day_start, day_end = _local_day_bounds(d)
    events = await _events_between(db, day_start, day_end)

    window_start = datetime.combine(d, WORK_START, tzinfo=_TZ).astimezone(timezone.utc)
    window_end = datetime.combine(d, WORK_END, tzinfo=_TZ).astimezone(timezone.utc)

    # 已經過去的時段不算空檔（避免在 15:00 還回報今天 09:00 有空）。
    # 只要「現在」已晚於工作窗開始就往後縮（整個窗都過了則由下一行守衛攔下）；
    # 查未來日期時 now 在窗前，不受影響。
    now_utc = _now_local().astimezone(timezone.utc)
    if window_start < now_utc:
        window_start = now_utc
    if window_start >= window_end:
        return f"{d.isoformat()} 的工作時間（09:00–18:00）已經過了，沒有可安排的空檔。"

    slots = find_free_slots(events, window_start, window_end, min_minutes=min_minutes)
    if not slots:
        return f"{d.isoformat()} 在 09:00–18:00 之間沒有達 {min_minutes} 分鐘的空檔。"

    parts = [f"{_fmt(s.start)}–{_fmt(s.end)}（{round(s.minutes / 60, 1)} 小時）" for s in slots]
    return f"{d.isoformat()} 的空檔：" + "、".join(parts)


# tool name → 執行函式
async def run_tool(db: AsyncSession, name: str, args: dict) -> str:
    if name == "get_schedule":
        return await get_schedule(db, args.get("date"), args.get("range", "day"))
    if name == "find_free_slots":
        return await find_free_slots_tool(db, args.get("date"), args.get("min_minutes", 30))
    return f"未知的工具：{name}"
