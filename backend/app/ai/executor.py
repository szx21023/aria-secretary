"""把 Claude 的 tool 呼叫對應到 DB 操作，回傳給模型閱讀的文字結果。

唯讀工具（get_schedule / find_free_slots）與寫入工具（create/reschedule/cancel
event、add/complete task、create/toggle reminder）。寫入工具成功時在 ToolResult.changed
標出改動的資源，讓 agent 推 state_changed 事件給前端即時刷新。
衝突策略：偵測到時間衝突就回報、不執行；使用者確認後由 Claude 帶 allow_conflict=true 重呼叫。
每個寫入工具各自 commit；整輪非原子是刻意取捨——衝突策略本就逐項確認，半套寫入（如加了待辦
但會議因衝突沒排）傷害小，不值得為原子性把 commit 延到 turn 邊界、犧牲即時刷新。
"""

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.weather import get_weather
from app.config import get_settings
from app.models.enums import EventCategory, ReminderKind, TaskPriority
from app.models.event import Event
from app.models.reminder import Reminder
from app.models.task import Task
from app.schemas.chat import ChangedResource
from app.services import life as life_service
from app.services.scheduling import detect_conflicts, find_free_slots

logger = logging.getLogger(__name__)

_TZ = ZoneInfo(get_settings().app_tz)

# 找空檔的工作時間窗（在地時間）
WORK_START = time(9, 0)
WORK_END = time(18, 0)

# 會改動資料的工具；用來判斷「呼叫了卻 changed=None」是真的 no-op（找不到/模糊/衝突/壞輸入）。
_WRITE_TOOLS = frozenset(
    {
        "create_event",
        "reschedule_event",
        "cancel_event",
        "add_task",
        "complete_task",
        "create_reminder",
        "toggle_reminder",
        "create_milestone",
        "set_milestone",
    }
)

# 里程碑只給日期時，預設排在當天這個時間、長度一小時（行事曆上才有個具體區塊）
MILESTONE_DEFAULT_TIME = time(9, 0)
MILESTONE_DURATION_MIN = 60


def _now_local() -> datetime:
    return datetime.now(_TZ)


def _parse_date(s: str | None) -> date:
    if not s:
        return _now_local().date()
    return date.fromisoformat(s)


def _local_day_bounds(d: date) -> tuple[datetime, datetime]:
    """回傳該在地日期的 [00:00, 隔日00:00) 對應的 UTC datetime。"""
    start = datetime.combine(d, time.min, tzinfo=_TZ).astimezone(UTC)
    end = datetime.combine(d + timedelta(days=1), time.min, tzinfo=_TZ).astimezone(UTC)
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
    now = _now_local().astimezone(UTC)
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
        lines.append(f"- {when} {e.title}（{e.category.value}，{_derive_status(e, now)}{loc}{ppl}）[id={e.id}]")
    return "\n".join(lines)


async def find_free_slots_tool(db: AsyncSession, date: str | None = None, min_minutes: int = 30) -> str:
    try:
        d = _parse_date(date)
    except ValueError:
        return f"日期格式無法解析：{date!r}，請用 YYYY-MM-DD，或省略代表今天。"
    day_start, day_end = _local_day_bounds(d)
    events = await _events_between(db, day_start, day_end)

    window_start = datetime.combine(d, WORK_START, tzinfo=_TZ).astimezone(UTC)
    window_end = datetime.combine(d, WORK_END, tzinfo=_TZ).astimezone(UTC)

    # 已經過去的時段不算空檔（避免在 15:00 還回報今天 09:00 有空）。
    # 只要「現在」已晚於工作窗開始就往後縮（整個窗都過了則由下一行守衛攔下）；
    # 查未來日期時 now 在窗前，不受影響。
    now_utc = _now_local().astimezone(UTC)
    if window_start < now_utc:
        window_start = now_utc
    if window_start >= window_end:
        return f"{d.isoformat()} 的工作時間（09:00–18:00）已經過了，沒有可安排的空檔。"

    slots = find_free_slots(events, window_start, window_end, min_minutes=min_minutes)
    if not slots:
        return f"{d.isoformat()} 在 09:00–18:00 之間沒有達 {min_minutes} 分鐘的空檔。"

    parts = [f"{_fmt(s.start)}–{_fmt(s.end)}（{round(s.minutes / 60, 1)} 小時）" for s in slots]
    return f"{d.isoformat()} 的空檔：" + "、".join(parts)


async def get_tasks(db: AsyncSession) -> str:
    rows = list(await db.scalars(select(Task).order_by(Task.done, Task.due_at.is_(None), Task.due_at)))
    if not rows:
        return "目前沒有任何待辦。"
    undone = sum(1 for t in rows if not t.done)
    lines = [f"待辦共 {len(rows)} 項（未完成 {undone}、已完成 {len(rows) - undone}）："]
    for t in rows:
        status = "已完成" if t.done else "未完成"
        prio = f"，{t.priority.value}" if t.priority else ""
        due = f"，到期 {_fmt_dt(t.due_at)}" if t.due_at else ""
        lines.append(f"- {t.title}（{status}{prio}{due}）")
    return "\n".join(lines)


async def get_reminders(db: AsyncSession) -> str:
    rows = list(await db.scalars(select(Reminder).order_by(Reminder.enabled.desc(), Reminder.trigger_at)))
    if not rows:
        return "目前沒有任何提醒。"
    lines = [f"提醒共 {len(rows)} 則："]
    for r in rows:
        state = "啟用中" if r.enabled else "已關閉"
        sub = f"，{r.subtitle}" if r.subtitle else ""
        when = f"，{_fmt_dt(r.trigger_at)}" if r.trigger_at else ""
        lines.append(f"- {r.title}（{state}，{r.kind.value}{sub}{when}）")
    return "\n".join(lines)


# ── 寫入工具 ────────────────────────────────────────────────────


@dataclass
class ToolResult:
    """工具執行結果。changed 標出被改動的資源（events/tasks/reminders），

    None 代表唯讀或未實際改動（例如偵測到衝突而暫不執行）——agent 只在 changed
    非 None 時推 state_changed，避免空操作觸發前端重抓。
    """

    text: str
    changed: ChangedResource | None = None


def _parse_dt(s: str) -> datetime:
    """ISO 字串 → UTC aware datetime；無時區資訊者視為在地時間。"""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_TZ)
    return dt.astimezone(UTC)


def _fmt_dt(dt: datetime) -> str:
    return dt.astimezone(_TZ).strftime("%m/%d %H:%M")


def _conflict_msg(conflicts: list[Event]) -> str:
    items = "、".join(f"{_fmt(c.start_at)}–{_fmt(c.end_at)} {c.title}" for c in conflicts)
    return f"時間衝突：與 {items} 重疊。"


async def _overlapping_events(
    db: AsyncSession, start: datetime, end: datetime, exclude_id: str | None = None
) -> list[Event]:
    # 半開區間重疊：start_at < end 且 end_at > start（相接不算）
    stmt = select(Event).where(Event.start_at < end, Event.end_at > start)
    if exclude_id is not None:
        stmt = stmt.where(Event.id != exclude_id)
    return list(await db.scalars(stmt))


async def create_event(
    db: AsyncSession,
    title: str,
    start_at: str,
    duration_min: int,
    category: str | None = None,
    location: str | None = None,
    attendees: int | None = None,
    allow_conflict: bool = False,
) -> ToolResult:
    try:
        start = _parse_dt(start_at)
    except ValueError:
        return ToolResult(f"開始時間無法解析：{start_at!r}，請用 ISO 格式如 2026-06-07T15:00。")
    if not duration_min or duration_min <= 0:
        return ToolResult("duration_min 必須是正整數（分鐘）。")
    try:
        cat = EventCategory(category) if category else EventCategory.meeting
    except ValueError:
        return ToolResult(f"未知的分類：{category!r}，可用：meeting/focus/meal/personal。")
    end = start + timedelta(minutes=duration_min)

    if not allow_conflict:
        conflicts = detect_conflicts(await _overlapping_events(db, start, end), start, end)
        if conflicts:
            return ToolResult(
                _conflict_msg(conflicts) + " 已暫不建立；若使用者確認仍要安排，帶 allow_conflict=true 再呼叫。"
            )

    db.add(
        Event(
            title=title,
            start_at=start,
            end_at=end,
            category=cat,
            location=location,
            attendees=attendees,
        )
    )
    await db.commit()
    return ToolResult(f"已新增行程：{_fmt_dt(start)}–{_fmt(end)} {title}。", changed="events")


async def reschedule_event(
    db: AsyncSession,
    event_id: str,
    new_start_at: str | None = None,
    delta_min: int | None = None,
    allow_conflict: bool = False,
) -> ToolResult:
    event = await db.get(Event, event_id)
    if event is None:
        return ToolResult(f"找不到 id={event_id} 的行程，請先用 get_schedule 確認。")
    duration = event.end_at - event.start_at
    if new_start_at:
        try:
            new_start = _parse_dt(new_start_at)
        except ValueError:
            return ToolResult(f"新開始時間無法解析：{new_start_at!r}，請用 ISO 格式。")
    elif delta_min is not None:
        new_start = event.start_at + timedelta(minutes=delta_min)
    else:
        return ToolResult("請提供 new_start_at（絕對時間）或 delta_min（相對分鐘）其中一個。")
    new_end = new_start + duration

    if not allow_conflict:
        conflicts = detect_conflicts(
            await _overlapping_events(db, new_start, new_end, event.id),
            new_start,
            new_end,
            exclude_id=event.id,
        )
        if conflicts:
            return ToolResult(
                _conflict_msg(conflicts) + " 已暫不改期；若使用者確認仍要改，帶 allow_conflict=true 再呼叫。"
            )

    event.start_at = new_start
    event.end_at = new_end
    await db.commit()
    return ToolResult(f"已改期：{event.title} → {_fmt_dt(new_start)}–{_fmt(new_end)}。", changed="events")


async def cancel_event(db: AsyncSession, event_id: str) -> ToolResult:
    event = await db.get(Event, event_id)
    if event is None:
        return ToolResult(f"找不到 id={event_id} 的行程。")
    label = f"{_fmt_dt(event.start_at)} {event.title}"
    await db.delete(event)
    await db.commit()
    return ToolResult(f"已取消：{label}。", changed="events")


async def add_task(db: AsyncSession, title: str, due_at: str | None = None, priority: str | None = None) -> ToolResult:
    due = None
    if due_at:
        try:
            due = _parse_dt(due_at)
        except ValueError:
            return ToolResult(f"到期時間無法解析：{due_at!r}，請用 ISO 格式或省略。")
    prio = None
    if priority:
        try:
            prio = TaskPriority(priority)
        except ValueError:
            return ToolResult(f"未知的優先級：{priority!r}，可用：high/medium/low。")
    db.add(Task(title=title, due_at=due, priority=prio))
    await db.commit()
    return ToolResult(f"已加入待辦：{title}。", changed="tasks")


async def complete_task(db: AsyncSession, query: str) -> ToolResult:
    rows = list(await db.scalars(select(Task)))
    # 先精確比對整個標題，唯一才退回子字串：避免短關鍵字偶然命中而默默改錯目標。
    # 模糊度看「全部符合數」而非只看未完成——一完成一未完成時也回報請確認，不擅自挑未完成那筆。
    matches = [t for t in rows if t.title == query] or [t for t in rows if query in t.title]
    if not matches:
        return ToolResult(f"找不到符合「{query}」的待辦。")
    if len(matches) > 1:
        names = "、".join(t.title for t in matches)
        return ToolResult(f"有多個符合「{query}」的待辦：{names}。請確認是哪一個。")
    task = matches[0]
    if task.done:
        return ToolResult(f"「{task.title}」已經是完成狀態了。")
    task.done = True
    await db.commit()
    return ToolResult(f"已完成待辦：{task.title}。", changed="tasks")


async def create_reminder(
    db: AsyncSession,
    title: str,
    subtitle: str | None = None,
    trigger_at: str | None = None,
    kind: str | None = None,
    recurrence: str | None = None,
) -> ToolResult:
    trig = None
    if trigger_at:
        try:
            trig = _parse_dt(trigger_at)
        except ValueError:
            return ToolResult(f"提醒時間無法解析：{trigger_at!r}，請用 ISO 格式或省略。")
    try:
        k = ReminderKind(kind) if kind else ReminderKind.meeting
    except ValueError:
        return ToolResult(f"未知的提醒類型：{kind!r}，可用：meeting/birthday/bill/health。")
    db.add(Reminder(title=title, subtitle=subtitle, trigger_at=trig, kind=k, recurrence=recurrence))
    await db.commit()
    suffix = f"（{recurrence}）" if recurrence else ""
    return ToolResult(f"已新增提醒：{title}{suffix}。", changed="reminders")


async def toggle_reminder(db: AsyncSession, query: str, enabled: bool) -> ToolResult:
    rows = list(await db.scalars(select(Reminder)))
    # 同 complete_task：精確標題優先，唯一才退子字串——關掉錯的提醒（漏掉帳單/健康通知）後果靜默。
    matches = [r for r in rows if r.title == query] or [r for r in rows if query in r.title]
    if not matches:
        return ToolResult(f"找不到符合「{query}」的提醒。")
    if len(matches) > 1:
        names = "、".join(r.title for r in matches)
        return ToolResult(f"有多個符合「{query}」的提醒：{names}。請確認是哪一個。")
    matches[0].enabled = enabled
    await db.commit()
    state = "開啟" if enabled else "關閉"
    return ToolResult(f"已{state}提醒：{matches[0].title}。", changed="reminders")


async def get_milestones(db: AsyncSession) -> str:
    """列出未來的里程碑與倒數天數；已設生日時附上屆時歲數。"""
    profile = await life_service.get_profile(db)
    items = await life_service.list_milestones(db, profile.birthday if profile else None)
    if not items:
        return "目前沒有標記任何人生里程碑。"
    lines = []
    for m in items:
        left = "就是今天" if m.days_left == 0 else f"剩 {m.days_left} 天"
        age = f"、屆時 {m.age_at} 歲" if m.age_at is not None else ""
        lines.append(f"- {m.title}（{m.target_date}，{left}{age}）[id={m.id}]")
    return "人生里程碑：\n" + "\n".join(lines)


async def create_milestone(
    db: AsyncSession,
    title: str,
    target_date: str,
    start_time: str | None = None,
    note: str | None = None,
) -> ToolResult:
    """建立標為里程碑的行程。不做衝突檢查——里程碑多為全天性質的目標，
    跟當天既有會議重疊很正常，攔下來只會多一輪無謂確認。"""
    try:
        day = date.fromisoformat(target_date)
    except ValueError:
        return ToolResult(f"日期無法解析：{target_date!r}，請用 YYYY-MM-DD 格式。")
    clock = MILESTONE_DEFAULT_TIME
    if start_time:
        try:
            clock = time.fromisoformat(start_time)
        except ValueError:
            return ToolResult(f"時間無法解析：{start_time!r}，請用 HH:MM 格式或省略。")

    # 人生頁只倒數今天之後的里程碑，過去的日期建了也永遠不會出現——
    # 與其回報成功卻查無此項，不如當場擋下並請使用者確認年份。
    days_left = (day - _now_local().date()).days
    if days_left < 0:
        return ToolResult(
            f"{day} 已經過去了，里程碑只倒數今天之後的日期，因此沒有建立。"
            "請確認年份是否正確；若是要記錄已完成的事，請改用一般行程。"
        )

    start = datetime.combine(day, clock, tzinfo=_TZ).astimezone(UTC)
    end = start + timedelta(minutes=MILESTONE_DURATION_MIN)
    db.add(
        Event(
            title=title,
            start_at=start,
            end_at=end,
            category=EventCategory.personal,
            note=note,
            is_milestone=True,
        )
    )
    await db.commit()
    left = "就是今天" if days_left == 0 else f"距今 {days_left} 天"
    return ToolResult(f"已記下里程碑：{title}（{day}，{left}）。", changed="events")


async def set_milestone(db: AsyncSession, query: str, is_milestone: bool) -> ToolResult:
    """標記／取消標記既有行程。比對策略同 complete_task：先精確、唯一才退回子字串。"""
    rows = list(await db.scalars(select(Event)))
    matches = [e for e in rows if e.title == query] or [e for e in rows if query in e.title]
    if not matches:
        return ToolResult(f"找不到符合「{query}」的行程。")
    if len(matches) > 1:
        names = "、".join(f"{_fmt_dt(e.start_at)} {e.title}" for e in matches)
        return ToolResult(f"有多個符合「{query}」的行程：{names}。請確認是哪一個。")
    event = matches[0]
    if event.is_milestone == is_milestone:
        state = "已經是里程碑了" if is_milestone else "本來就不是里程碑"
        return ToolResult(f"「{event.title}」{state}。")
    event.is_milestone = is_milestone
    await db.commit()
    action = "已標為里程碑" if is_milestone else "已取消里程碑標記（行程保留）"
    return ToolResult(f"「{event.title}」{action}。", changed="events")


async def run_tool(db: AsyncSession, name: str, args: dict) -> ToolResult:
    result = await _dispatch(db, name, args)
    # 寫入工具被呼叫卻沒改到資料（找不到/模糊/衝突/壞輸入），留一筆 log。
    # 否則「模型把 no-op 講成已完成」在 server 端只看得到工具被呼叫、看不出它其實沒做成。
    if name in _WRITE_TOOLS and result.changed is None:
        logger.info("tool %s no-op: %s", name, result.text)
    return result


# tool name → 執行函式
async def _dispatch(db: AsyncSession, name: str, args: dict) -> ToolResult:
    if name == "get_schedule":
        return ToolResult(await get_schedule(db, args.get("date"), args.get("range", "day")))
    if name == "find_free_slots":
        return ToolResult(await find_free_slots_tool(db, args.get("date"), args.get("min_minutes", 30)))
    if name == "get_tasks":
        return ToolResult(await get_tasks(db))
    if name == "get_reminders":
        return ToolResult(await get_reminders(db))
    if name == "get_weather":
        return ToolResult(await get_weather(args["location"], args.get("date")))
    if name == "create_event":
        return await create_event(
            db,
            args["title"],
            args["start_at"],
            args["duration_min"],
            args.get("category"),
            args.get("location"),
            args.get("attendees"),
            args.get("allow_conflict", False),
        )
    if name == "reschedule_event":
        return await reschedule_event(
            db,
            args["event_id"],
            args.get("new_start_at"),
            args.get("delta_min"),
            args.get("allow_conflict", False),
        )
    if name == "cancel_event":
        return await cancel_event(db, args["event_id"])
    if name == "add_task":
        return await add_task(db, args["title"], args.get("due_at"), args.get("priority"))
    if name == "complete_task":
        return await complete_task(db, args["query"])
    if name == "create_reminder":
        return await create_reminder(
            db,
            args["title"],
            args.get("subtitle"),
            args.get("trigger_at"),
            args.get("kind"),
            args.get("recurrence"),
        )
    if name == "toggle_reminder":
        return await toggle_reminder(db, args["query"], args["enabled"])
    if name == "get_milestones":
        return ToolResult(await get_milestones(db))
    if name == "create_milestone":
        return await create_milestone(
            db,
            args["title"],
            args["target_date"],
            args.get("start_time"),
            args.get("note"),
        )
    if name == "set_milestone":
        return await set_milestone(db, args["query"], args["is_milestone"])
    return ToolResult(f"未知的工具：{name}")
