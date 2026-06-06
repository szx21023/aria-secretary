"""把原型的 INITIAL_EVENTS / TASKS / REMINDERS 轉成以「今天」為錨點的真實 datetime。

原型情境是週五（day 5）為主秀日，day 1-7 對應週一到週日。
這裡把主秀日對齊到「真實今天」，其餘日子用相對位移保留原本的排版，
所有 datetime 以 app 時區（預設 Asia/Taipei）建立後存成 UTC。
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.enums import (
    EventCategory,
    EventStatus,
    MessageRole,
    ReminderKind,
    TaskPriority,
)
from app.models.chat import Conversation, Message
from app.models.event import Event
from app.models.reminder import Reminder
from app.models.task import Task

settings = get_settings()
_TZ = ZoneInfo(settings.app_tz)


def _midnight_today_local() -> datetime:
    now = datetime.now(_TZ)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _at(base: datetime, day_offset: int, hour: int, minute: int = 0) -> datetime:
    """以本地午夜為基準，加上日/時/分，回傳 UTC aware datetime。"""
    local = base + timedelta(days=day_offset, hours=hour, minutes=minute)
    return local.astimezone(timezone.utc)


def _build_events(base: datetime) -> list[Event]:
    # (day_offset, hour, minute, duration_min, title, category, location, attendees, note)
    rows = [
        (0, 9, 0, 30, "晨間回顧 ＋ 規劃今日", EventCategory.personal, "個人時間", None, None),
        (0, 10, 30, 60, "與設計團隊週會", EventCategory.meeting, "Google Meet", 5, None),
        (0, 12, 30, 60, "午餐 · 與 Kevin", EventCategory.meal, "青葉餐廳 · 信義區", None, None),
        (0, 15, 0, 45, "產品 Roadmap 簡報", EventCategory.meeting, "會議室 A", 8, "已由秘書從 14:00 順延"),
        (0, 16, 30, 60, "健身 · 河濱跑步", EventCategory.personal, "大佳河濱公園", None, None),
        (0, 19, 30, 90, "晚餐預約 · 鮨処さくら", EventCategory.meal, "中山區 · 4 位", None, None),
        (-4, 11, 0, 60, "季度策略會議", EventCategory.meeting, "會議室 B", 12, None),
        (-3, 14, 0, 90, "深度工作 · 撰寫提案", EventCategory.focus, "勿擾", None, None),
        (-2, 9, 30, 45, "1:1 · 與 Mia", EventCategory.meeting, "視訊", 2, None),
        (-2, 18, 0, 60, "瑜珈課", EventCategory.personal, "信義運動中心", None, None),
        (-1, 13, 0, 60, "與投資人午餐", EventCategory.meal, "樂朋小館", None, None),
        (1, 10, 0, 120, "媽媽生日 · 家庭聚會", EventCategory.personal, "家", None, None),
    ]
    events: list[Event] = []
    for day, hh, mm, dur, title, cat, loc, ppl, note in rows:
        start = _at(base, day, hh, mm)
        events.append(
            Event(
                title=title,
                start_at=start,
                end_at=start + timedelta(minutes=dur),
                category=cat,
                location=loc,
                attendees=ppl,
                status=EventStatus.scheduled,  # live/done 由 M2 依真實時間動態推導
                note=note,
            )
        )
    return events


def _build_tasks(base: datetime) -> list[Task]:
    # (title, due_at_or_None, priority, done)
    rows = [
        ("回覆投資人月報信件", _at(base, 0, 17, 0), TaskPriority.high, False),
        ("確認下週東京出差機票", _at(base, 0, 23, 59), TaskPriority.high, False),
        ("審閱合作合約 v3", _at(base, 1, 23, 59), TaskPriority.medium, False),
        ("訂媽媽生日禮物", _at(base, 2, 23, 59), TaskPriority.high, False),
        ("預訂牙醫回診", _at(base, 3, 23, 59), None, False),
        ("整理設計週會筆記", _at(base, 0, 23, 59), None, True),
        ("更新團隊 OKR 文件", _at(base, 3, 23, 59), TaskPriority.medium, True),
    ]
    return [Task(title=t, due_at=d, priority=p, done=done) for t, d, p, done in rows]


def _build_reminders(base: datetime) -> list[Reminder]:
    # (title, subtitle, trigger_at, recurrence, kind, enabled)
    rows = [
        ("與設計團隊週會即將開始", "10:30 · Google Meet", _at(base, 0, 10, 15), None, ReminderKind.meeting, True),
        ("產品 Roadmap 簡報", "15:00 · 提前 1 小時提醒", _at(base, 0, 14, 0), None, ReminderKind.meeting, True),
        ("媽媽生日", "記得準備禮物與蛋糕", _at(base, 2, 9, 0), None, ReminderKind.birthday, True),
        ("信用卡帳單繳費", "本期應繳 NT$ 18,420", _at(base, 5, 9, 0), None, ReminderKind.bill, False),
        ("每日服用維他命", "早晨例行", _at(base, 0, 8, 0), "daily", ReminderKind.health, True),
    ]
    return [
        Reminder(title=t, subtitle=s, trigger_at=tr, recurrence=rec, kind=k, enabled=on)
        for t, s, tr, rec, k, on in rows
    ]


async def seed_if_empty(db: AsyncSession) -> bool:
    """若 events 表為空才 seed。回傳是否實際寫入。"""
    count = await db.scalar(select(func.count()).select_from(Event))
    if count and count > 0:
        return False

    base = _midnight_today_local()
    db.add_all(_build_events(base))
    db.add_all(_build_tasks(base))
    db.add_all(_build_reminders(base))

    convo = Conversation(title="Aria")
    convo.messages.append(
        Message(
            role=MessageRole.assistant,
            content="早安 ☀️ 今天有 6 個行程、4 項待辦，下午稍微緊湊。需要我幫你安排什麼嗎？",
        )
    )
    db.add(convo)

    await db.commit()
    return True
