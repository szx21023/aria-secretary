"""背景推播排程器：提醒到點、行程即將開始時主動 push 到 LINE。

lifespan 啟動一個 asyncio 迴圈，每 notifier_interval_sec 秒掃一次：
  - 提醒：enabled 且 trigger_at 已到、尚未推播（fired_at 為 None）→ push，標 fired_at。
  - 行程：start_at 落在「現在～現在+lead」且尚未推播（notified_at 為 None）→ push，標 notified_at。

防重複靠 fired_at / notified_at 落地（重啟也不會重推）。為避免首次啟動或停機後復活時
把一堆「早就過期」的項目一次全推出去，過了 _STALE 視窗才到點的項目只「標記、不推播」。

週期性提醒（recurrence 非空）MVP 視為一次性：推一次後就標 fired_at，不自動重排下次。
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import AsyncSessionLocal
from app.line import client
from app.models.event import Event
from app.models.reminder import Reminder
from app.services.conversation import get_or_create_conversation

logger = logging.getLogger(__name__)

_TZ = ZoneInfo(get_settings().app_tz)
# 到點時間比現在早超過這個視窗的項目，視為「過期」：只標記不推播，免得復活時洗版。
_STALE = timedelta(minutes=10)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fmt(dt: datetime) -> str:
    return dt.astimezone(_TZ).strftime("%H:%M")


async def _push_target(db: AsyncSession) -> str | None:
    """推播收件人：優先用設定釘死的，否則用最後跟 bot 講過話的人。"""
    settings = get_settings()
    if settings.line_push_user_id:
        return settings.line_push_user_id
    convo = await get_or_create_conversation(db)
    return convo.line_user_id


async def process_due(db: AsyncSession, now: datetime | None = None) -> list[str]:
    """掃描並推播到點的提醒與即將開始的行程；回傳實際送出的訊息（供測試斷言）。

    沒有可推播的收件人時直接返回（不標記），等使用者之後接上 LINE 再處理待推項目。
    """
    now = now or _now()
    target = await _push_target(db)
    if not target:
        return []

    settings = get_settings()
    token = settings.line_channel_access_token
    lead = timedelta(minutes=settings.event_reminder_lead_min)
    sent: list[str] = []

    # ── 提醒：trigger_at 已到、未推播 ──────────────────────────
    reminders = await db.scalars(
        select(Reminder).where(
            Reminder.enabled.is_(True),
            Reminder.fired_at.is_(None),
            Reminder.trigger_at.is_not(None),
            Reminder.trigger_at <= now,
        )
    )
    for r in reminders:
        r.fired_at = now  # 不論推不推都標記，避免下輪重判
        if now - r.trigger_at <= _STALE:
            msg = f"🔔 提醒：{r.title}" + (f"\n{r.subtitle}" if r.subtitle else "")
            if await client.push(token, target, msg):
                sent.append(msg)
        else:
            logger.info("提醒「%s」已過期（trigger=%s），標記不推", r.title, r.trigger_at)

    # ── 行程：start_at 在 [now, now+lead]、未推播 ─────────────
    events = await db.scalars(
        select(Event).where(
            Event.notified_at.is_(None),
            Event.start_at <= now + lead,
        )
    )
    for e in events:
        e.notified_at = now
        if e.start_at < now - _STALE:
            logger.info("行程「%s」已過期（start=%s），標記不推", e.title, e.start_at)
            continue
        if e.start_at < now:
            # 已經開始（但還在 STALE 視窗內）：標記即可，不推「即將開始」這種馬後砲。
            continue
        mins = round((e.start_at - now).total_seconds() / 60)
        when = _fmt(e.start_at)
        loc = f"\n📍 {e.location}" if e.location else ""
        msg = f"📅 行程即將開始（約 {mins} 分鐘後）\n{when} {e.title}{loc}"
        if await client.push(token, target, msg):
            sent.append(msg)

    await db.commit()
    return sent


async def run_notifier() -> None:
    """背景常駐迴圈。被 lifespan 以 asyncio task 啟動，shutdown 時 cancel。"""
    interval = get_settings().notifier_interval_sec
    logger.info("推播排程器啟動，每 %d 秒掃描", interval)
    while True:
        try:
            await asyncio.sleep(interval)
            async with AsyncSessionLocal() as db:
                sent = await process_due(db)
            if sent:
                logger.info("本輪推播 %d 則", len(sent))
        except asyncio.CancelledError:
            logger.info("推播排程器停止")
            raise
        except Exception:
            # 單輪失敗（DB 暫時故障、LINE 5xx）不該讓整個排程器死掉；記 log 後下輪再試。
            logger.exception("推播排程器本輪失敗，續跑")
