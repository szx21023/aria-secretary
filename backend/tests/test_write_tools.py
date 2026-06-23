"""M4 寫入工具測試：create/reschedule/cancel event、add/complete task、

create/toggle reminder。重點鎖住：成功時 changed 標對資源、衝突回報而不動手、
allow_conflict 可覆寫、找不到/模糊/壞輸入回友善訊息而非拋例外、半開區間相接不算衝突。
事件時間用 executor._TZ 建構後轉 UTC，與正式儲存方式一致。
"""

import logging
from datetime import UTC, datetime
from typing import get_args

import pytest
from sqlalchemy import select

from app.ai import executor
from app.ai.executor import (
    _TZ,
    add_task,
    cancel_event,
    complete_task,
    create_event,
    create_reminder,
    get_reminders,
    get_schedule,
    get_tasks,
    reschedule_event,
    run_tool,
    toggle_reminder,
)
from app.models.enums import EventCategory, ReminderKind, TaskPriority
from app.models.event import Event
from app.models.reminder import Reminder
from app.models.task import Task

pytestmark = pytest.mark.asyncio

UTC = UTC


def _local(y, m, d, hh, mm=0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=_TZ)


def _utc(y, m, d, hh, mm=0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=UTC)


async def _seed_event(db, title, start_local, end_local) -> Event:
    ev = Event(
        title=title,
        start_at=start_local.astimezone(UTC),
        end_at=end_local.astimezone(UTC),
        category=EventCategory.meeting,
    )
    db.add(ev)
    await db.commit()
    await db.refresh(ev)
    return ev


async def _seed_task(db, title, done=False) -> Task:
    t = Task(title=title, done=done)
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


async def _seed_reminder(db, title, enabled=True) -> Reminder:
    r = Reminder(title=title, enabled=enabled)
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return r


async def _all(db, model):
    return list(await db.scalars(select(model)))


# ── create_event ───────────────────────────────────────────────


async def test_create_event_success(db):
    res = await create_event(db, "新會議", "2026-06-07T15:00", 60)
    assert res.changed == "events"
    rows = await _all(db, Event)
    assert len(rows) == 1
    assert rows[0].title == "新會議"
    # 15:00 Asia/Taipei → 07:00 UTC，時長 60 分
    assert rows[0].start_at == _utc(2026, 6, 7, 7)
    assert rows[0].end_at == _utc(2026, 6, 7, 8)


async def test_create_event_conflict_reports_without_creating(db):
    await _seed_event(db, "既有", _local(2026, 6, 7, 15), _local(2026, 6, 7, 16))
    res = await create_event(db, "撞期", "2026-06-07T15:30", 60)
    assert res.changed is None
    assert "衝突" in res.text
    assert len(await _all(db, Event)) == 1  # 沒有建立


async def test_create_event_allow_conflict_creates(db):
    await _seed_event(db, "既有", _local(2026, 6, 7, 15), _local(2026, 6, 7, 16))
    res = await create_event(db, "硬排", "2026-06-07T15:30", 60, allow_conflict=True)
    assert res.changed == "events"
    assert len(await _all(db, Event)) == 2


async def test_create_event_adjacent_is_not_conflict(db):
    await _seed_event(db, "既有", _local(2026, 6, 7, 15), _local(2026, 6, 7, 16))
    res = await create_event(db, "緊接", "2026-06-07T16:00", 30)  # 16:00 接在 16:00 結束後
    assert res.changed == "events"


async def test_create_event_front_adjacent_is_not_conflict(db):
    # 半開區間的另一邊：新行程結束時間正好等於既有行程開始時間，不算衝突
    await _seed_event(db, "既有", _local(2026, 6, 7, 16), _local(2026, 6, 7, 17))
    res = await create_event(db, "前接", "2026-06-07T15:00", 60)  # 15:00–16:00 緊貼 16:00 開始前
    assert res.changed == "events"


async def test_create_event_bad_start(db):
    res = await create_event(db, "x", "not-a-time", 60)
    assert res.changed is None and "無法解析" in res.text


async def test_create_event_bad_duration(db):
    res = await create_event(db, "x", "2026-06-07T15:00", 0)
    assert res.changed is None and "duration_min" in res.text


async def test_create_event_bad_category(db):
    res = await create_event(db, "x", "2026-06-07T15:00", 60, category="party")
    assert res.changed is None and "分類" in res.text


# ── reschedule_event ───────────────────────────────────────────


async def test_reschedule_by_delta_keeps_duration(db):
    ev = await _seed_event(db, "簡報", _local(2026, 6, 7, 14), _local(2026, 6, 7, 15))
    res = await reschedule_event(db, ev.id, delta_min=60)
    assert res.changed == "events"
    await db.refresh(ev)
    assert ev.start_at == _utc(2026, 6, 7, 7)  # 15:00 local
    assert ev.end_at == _utc(2026, 6, 7, 8)  # 維持 1 小時


async def test_reschedule_by_new_start(db):
    ev = await _seed_event(db, "簡報", _local(2026, 6, 7, 14), _local(2026, 6, 7, 15))
    res = await reschedule_event(db, ev.id, new_start_at="2026-06-08T10:00")
    assert res.changed == "events"
    await db.refresh(ev)
    assert ev.start_at == _utc(2026, 6, 8, 2)  # 10:00 local → 02:00 UTC


async def test_reschedule_not_found(db):
    res = await reschedule_event(db, "nope", delta_min=30)
    assert res.changed is None and "找不到" in res.text


async def test_reschedule_requires_target_time(db):
    ev = await _seed_event(db, "x", _local(2026, 6, 7, 14), _local(2026, 6, 7, 15))
    res = await reschedule_event(db, ev.id)
    assert res.changed is None and "new_start_at" in res.text


async def test_reschedule_conflict_reports_without_moving(db):
    await _seed_event(db, "A", _local(2026, 6, 7, 9), _local(2026, 6, 7, 10))
    b = await _seed_event(db, "B", _local(2026, 6, 7, 11), _local(2026, 6, 7, 12))
    res = await reschedule_event(db, b.id, new_start_at="2026-06-07T09:30")
    assert res.changed is None and "衝突" in res.text
    await db.refresh(b)
    assert b.start_at == _utc(2026, 6, 7, 3)  # 11:00 local，未被改動


async def test_reschedule_excludes_self_from_conflict(db):
    ev = await _seed_event(db, "X", _local(2026, 6, 7, 9), _local(2026, 6, 7, 10))
    # 改到與自己原時段重疊的 09:30 不該被自己擋下
    res = await reschedule_event(db, ev.id, new_start_at="2026-06-07T09:30")
    assert res.changed == "events"


async def test_reschedule_delta_excludes_self(db):
    ev = await _seed_event(db, "X", _local(2026, 6, 7, 9), _local(2026, 6, 7, 10))
    res = await reschedule_event(db, ev.id, delta_min=15)  # 09:15–10:15 與自己原時段重疊
    assert res.changed == "events"


async def test_reschedule_allow_conflict_overrides(db):
    await _seed_event(db, "A", _local(2026, 6, 7, 9), _local(2026, 6, 7, 10))
    b = await _seed_event(db, "B", _local(2026, 6, 7, 11), _local(2026, 6, 7, 12))
    res = await reschedule_event(db, b.id, new_start_at="2026-06-07T09:30", allow_conflict=True)
    assert res.changed == "events"
    await db.refresh(b)
    assert b.start_at == _utc(2026, 6, 7, 1, 30)  # 09:30 local，照排


async def test_reschedule_new_start_takes_precedence_over_delta(db):
    ev = await _seed_event(db, "X", _local(2026, 6, 7, 14), _local(2026, 6, 7, 15))
    res = await reschedule_event(db, ev.id, new_start_at="2026-06-08T10:00", delta_min=999)
    assert res.changed == "events"
    await db.refresh(ev)
    assert ev.start_at == _utc(2026, 6, 8, 2)  # 用 new_start_at，delta_min 被忽略


# ── cancel_event ───────────────────────────────────────────────


async def test_cancel_event(db):
    ev = await _seed_event(db, "午餐", _local(2026, 6, 7, 12), _local(2026, 6, 7, 13))
    res = await cancel_event(db, ev.id)
    assert res.changed == "events"
    assert await _all(db, Event) == []


async def test_cancel_event_not_found(db):
    res = await cancel_event(db, "nope")
    assert res.changed is None and "找不到" in res.text


# ── add_task ───────────────────────────────────────────────────


async def test_add_task(db):
    res = await add_task(db, "回信", due_at="2026-06-07T17:00", priority="high")
    assert res.changed == "tasks"
    t = (await _all(db, Task))[0]
    assert t.title == "回信" and t.priority == TaskPriority.high and t.done is False
    assert t.due_at == _utc(2026, 6, 7, 9)  # 17:00 local


async def test_add_task_bad_priority(db):
    res = await add_task(db, "x", priority="urgent")
    assert res.changed is None and "優先級" in res.text


# ── complete_task ──────────────────────────────────────────────


async def test_complete_task(db):
    await _seed_task(db, "確認東京出差機票")
    res = await complete_task(db, "機票")
    assert res.changed == "tasks"
    assert (await _all(db, Task))[0].done is True


async def test_complete_task_not_found(db):
    res = await complete_task(db, "不存在")
    assert res.changed is None and "找不到" in res.text


async def test_complete_task_already_done(db):
    await _seed_task(db, "已完成事項", done=True)
    res = await complete_task(db, "已完成")
    assert res.changed is None and "已經是完成" in res.text


async def test_complete_task_ambiguous(db):
    await _seed_task(db, "買牛奶")
    await _seed_task(db, "買雞蛋")
    res = await complete_task(db, "買")
    assert res.changed is None and "多個" in res.text


async def test_complete_task_prefers_exact_title(db):
    await _seed_task(db, "報告")  # 完整標題
    await _seed_task(db, "週報告")  # 子字串也含「報告」
    res = await complete_task(db, "報告")
    assert res.changed == "tasks"  # 精確命中優先，不視為模糊
    done = [t.title for t in await _all(db, Task) if t.done]
    assert done == ["報告"]


async def test_complete_task_ambiguous_includes_done_matches(db):
    # 一完成一未完成都含「買」→ 視為模糊而回報，不擅自挑未完成那筆
    await _seed_task(db, "買牛奶", done=True)
    await _seed_task(db, "買雞蛋", done=False)
    res = await complete_task(db, "買")
    assert res.changed is None and "多個" in res.text
    done = [t.title for t in await _all(db, Task) if t.done]
    assert done == ["買牛奶"]  # 雞蛋沒被動


async def test_complete_task_substring_leaves_others_untouched(db):
    await _seed_task(db, "買牛奶")
    await _seed_task(db, "寫報告")
    res = await complete_task(db, "牛奶")
    assert res.changed == "tasks"
    done = [t.title for t in await _all(db, Task) if t.done]
    assert done == ["買牛奶"]  # 報告沒被碰


# ── create_reminder ────────────────────────────────────────────


async def test_create_reminder(db):
    res = await create_reminder(db, "吃維他命", subtitle="早晨例行", trigger_at="2026-06-07T08:00", kind="health")
    assert res.changed == "reminders"
    r = (await _all(db, Reminder))[0]
    assert r.title == "吃維他命" and r.kind == ReminderKind.health and r.enabled is True
    assert r.recurrence is None  # 一次性提醒不帶週期


async def test_create_reminder_bad_kind(db):
    res = await create_reminder(db, "x", kind="party")
    assert res.changed is None and "類型" in res.text


async def test_create_reminder_with_recurrence(db):
    res = await create_reminder(db, "吃藥", trigger_at="2026-06-07T23:00", recurrence="每天", kind="health")
    assert res.changed == "reminders"
    assert "每天" in res.text  # 回覆帶出週期
    r = (await _all(db, Reminder))[0]
    assert r.recurrence == "每天" and r.kind == ReminderKind.health


# ── toggle_reminder ────────────────────────────────────────────


async def test_toggle_reminder_off(db):
    await _seed_reminder(db, "信用卡帳單繳費", enabled=True)
    res = await toggle_reminder(db, "帳單", enabled=False)
    assert res.changed == "reminders"
    assert (await _all(db, Reminder))[0].enabled is False


async def test_toggle_reminder_not_found(db):
    res = await toggle_reminder(db, "x", enabled=True)
    assert res.changed is None and "找不到" in res.text


async def test_toggle_reminder_ambiguous(db):
    await _seed_reminder(db, "提醒甲")
    await _seed_reminder(db, "提醒乙")
    res = await toggle_reminder(db, "提醒", enabled=False)
    assert res.changed is None and "多個" in res.text


async def test_toggle_reminder_prefers_exact_title(db):
    await _seed_reminder(db, "帳單")
    await _seed_reminder(db, "信用卡帳單繳費")
    res = await toggle_reminder(db, "帳單", enabled=False)  # 精確命中「帳單」，不視為模糊
    assert res.changed == "reminders"
    off = [r.title for r in await _all(db, Reminder) if not r.enabled]
    assert off == ["帳單"]


# ── get_schedule 帶 id + run_tool 寫入 dispatch ────────────────


async def test_get_schedule_includes_event_id(db, monkeypatch):
    monkeypatch.setattr(executor, "_now_local", lambda: _local(2026, 6, 7, 8))
    ev = await _seed_event(db, "會議", _local(2026, 6, 7, 10), _local(2026, 6, 7, 11))
    out = await get_schedule(db, date="2026-06-07")
    assert f"[id={ev.id}]" in out  # Claude 要靠這個 id 去改期/取消


async def test_run_tool_create_event_marks_changed(db):
    res = await run_tool(db, "create_event", {"title": "x", "start_at": "2026-06-07T15:00", "duration_min": 30})
    assert res.changed == "events"


async def test_run_tool_complete_task_marks_changed(db):
    await _seed_task(db, "做完的事")
    res = await run_tool(db, "complete_task", {"query": "做完"})
    assert res.changed == "tasks"


async def test_run_tool_logs_write_noop(db, caplog):
    # 寫入工具沒做成時要留 log，讓「模型謊稱已完成」在 server 端查得出來
    with caplog.at_level(logging.INFO, logger="app.ai.executor"):
        res = await run_tool(db, "complete_task", {"query": "不存在的待辦"})
    assert res.changed is None
    assert any("no-op" in r.message and "complete_task" in r.message for r in caplog.records)


async def test_run_tool_no_noop_log_when_write_succeeds(db, caplog):
    await _seed_task(db, "真的做完")
    with caplog.at_level(logging.INFO, logger="app.ai.executor"):
        res = await run_tool(db, "complete_task", {"query": "真的做完"})
    assert res.changed == "tasks"
    assert not any("no-op" in r.message for r in caplog.records)


# ── get_tasks / get_reminders（唯讀） ──────────────────────────


async def test_get_tasks_empty(db):
    assert "沒有任何待辦" in await get_tasks(db)


async def test_get_tasks_lists_with_status(db):
    await _seed_task(db, "回信", done=False)
    await _seed_task(db, "已交報告", done=True)
    out = await get_tasks(db)
    assert "回信" in out and "未完成" in out
    assert "已交報告" in out and "已完成" in out
    assert "未完成 1" in out and "已完成 1" in out  # 鬆綁：不綁死 header 標點/順序


async def test_get_reminders_lists_with_state(db):
    await _seed_reminder(db, "吃藥", enabled=True)
    await _seed_reminder(db, "繳費", enabled=False)
    out = await get_reminders(db)
    assert "吃藥" in out and "啟用中" in out
    assert "繳費" in out and "已關閉" in out


async def test_get_tasks_renders_due_in_local_time(db):
    # 鎖住讀取路徑的 _fmt_dt 分支（TZ 敏感）：17:00 台北應原樣顯示，不被當 UTC
    db.add(Task(title="繳稅", due_at=_local(2026, 6, 7, 17).astimezone(UTC)))
    await db.commit()
    out = await get_tasks(db)
    assert "到期 06/07 17:00" in out


async def test_get_reminders_renders_trigger_in_local_time(db):
    db.add(Reminder(title="開會提醒", trigger_at=_local(2026, 6, 7, 9, 30).astimezone(UTC)))
    await db.commit()
    out = await get_reminders(db)
    assert "06/07 09:30" in out


async def test_run_tool_get_tasks_is_readonly(db):
    await _seed_task(db, "x")
    res = await run_tool(db, "get_tasks", {})
    assert res.changed is None and "待辦" in res.text


async def test_run_tool_get_reminders_is_readonly(db):
    await _seed_reminder(db, "x")
    res = await run_tool(db, "get_reminders", {})
    assert res.changed is None and "提醒" in res.text


async def test_changed_resource_literal_pins_the_set():
    # 釘住 executor changed / SSE resource / 前端 query key 三方共用的字串集合，防止默默漂移
    from app.schemas.chat import ChangedResource

    assert set(get_args(ChangedResource)) == {"events", "tasks", "reminders"}
