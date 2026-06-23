"""executor 工具層測試：dispatch、時區日界、以及 find_free_slots 不回報過去時段（#7）。

時間相關的測試把 executor._now_local monkeypatch 成固定時刻，確保可重現。
事件時間一律用 executor._TZ（=設定的 app_tz）建構，避免硬編時區。
"""

from datetime import UTC, datetime

import pytest

from app.ai import executor
from app.ai.executor import (
    _TZ,
    find_free_slots_tool,
    get_schedule,
    run_tool,
)
from app.models.enums import EventCategory
from app.models.event import Event

pytestmark = pytest.mark.asyncio


def _local(y, m, d, hh, mm=0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=_TZ)


def _freeze(monkeypatch, dt: datetime) -> None:
    monkeypatch.setattr(executor, "_now_local", lambda: dt)


async def _add_event(db, title, start_local, end_local, **kw) -> Event:
    ev = Event(
        title=title,
        start_at=start_local.astimezone(UTC),
        end_at=end_local.astimezone(UTC),
        category=kw.pop("category", EventCategory.meeting),
        **kw,
    )
    db.add(ev)
    await db.commit()
    return ev


# ── get_schedule ───────────────────────────────────────────────


async def test_get_schedule_empty(db, monkeypatch):
    _freeze(monkeypatch, _local(2026, 6, 5, 11))
    out = await get_schedule(db)
    assert "沒有任何行程" in out


async def test_get_schedule_lists_event_with_status(db, monkeypatch):
    _freeze(monkeypatch, _local(2026, 6, 5, 11))
    await _add_event(db, "晨會", _local(2026, 6, 5, 9), _local(2026, 6, 5, 10))
    await _add_event(db, "午餐", _local(2026, 6, 5, 12), _local(2026, 6, 5, 13))
    out = await get_schedule(db)
    assert "晨會" in out and "午餐" in out
    assert "共 2 個行程" in out
    assert "已結束" in out  # 09–10 在 11:00 看已結束
    assert "未開始" in out  # 12–13 在 11:00 看未開始


async def test_get_schedule_in_progress_status(db, monkeypatch):
    # 補齊 _derive_status 的中間分支：now 落在 start 與 end 之間 → 進行中
    _freeze(monkeypatch, _local(2026, 6, 5, 9, 30))
    await _add_event(db, "正在開的會", _local(2026, 6, 5, 9), _local(2026, 6, 5, 10))
    out = await get_schedule(db)
    assert "進行中" in out


async def test_get_schedule_day_boundary_respects_timezone(db, monkeypatch):
    """在地 06/06 01:00 的事件（UTC 仍是 06/05），查 06/06 必須查得到。"""
    _freeze(monkeypatch, _local(2026, 6, 6, 0, 30))
    await _add_event(db, "深夜加班", _local(2026, 6, 6, 1), _local(2026, 6, 6, 2))
    out_06 = await get_schedule(db, date="2026-06-06")
    assert "深夜加班" in out_06
    # 同一筆不該出現在前一天
    out_05 = await get_schedule(db, date="2026-06-05")
    assert "深夜加班" not in out_05


async def test_get_schedule_week_range(db, monkeypatch):
    _freeze(monkeypatch, _local(2026, 6, 5, 11))  # 週五
    await _add_event(db, "上週日", _local(2026, 5, 31, 18), _local(2026, 5, 31, 19))
    await _add_event(db, "週一會", _local(2026, 6, 1, 9), _local(2026, 6, 1, 10))
    await _add_event(db, "週日聚", _local(2026, 6, 7, 18), _local(2026, 6, 7, 19))
    await _add_event(db, "下週一", _local(2026, 6, 8, 9), _local(2026, 6, 8, 10))
    out = await get_schedule(db, range="week")
    assert "週一會" in out and "週日聚" in out
    assert "上週日" not in out  # 下界：落在前一週，超出 6/1–6/7
    assert "下週一" not in out  # 上界：落在下一週，超出 6/1–6/7


async def test_get_schedule_bad_date_returns_message_not_raise(db):
    out = await get_schedule(db, date="not-a-date")
    assert "無法解析" in out


# ── find_free_slots_tool（含 #7 過去時段裁切）─────────────────


async def test_find_free_slots_basic_before_work(db, monkeypatch):
    _freeze(monkeypatch, _local(2026, 6, 5, 8))  # 上班前問 → 整個工作窗都算
    await _add_event(db, "會議", _local(2026, 6, 5, 10), _local(2026, 6, 5, 11))
    out = await find_free_slots_tool(db)
    assert "09:00" in out  # 09–10 仍是空檔
    assert "11:00" in out


async def test_find_free_slots_skips_past_when_today(db, monkeypatch):
    """#7：下午 15:00 問今天空檔，不該回報已過去的 09:00。"""
    _freeze(monkeypatch, _local(2026, 6, 5, 15))
    out = await find_free_slots_tool(db)  # 無任何行程
    assert "09:00" not in out
    assert "15:00" in out  # 從現在起算


async def test_find_free_slots_after_work_hours(db, monkeypatch):
    _freeze(monkeypatch, _local(2026, 6, 5, 20))  # 工作時間已過
    out = await find_free_slots_tool(db)
    assert "已經過了" in out


async def test_find_free_slots_future_day_not_clamped(db, monkeypatch):
    """查未來日期不受『現在』影響，整個工作窗都算空檔。"""
    _freeze(monkeypatch, _local(2026, 6, 5, 15))
    out = await find_free_slots_tool(db, date="2026-06-08")
    assert "09:00" in out  # 未來日的早上仍是空檔


async def test_find_free_slots_bad_date(db):
    out = await find_free_slots_tool(db, date="2026/06/05")  # 斜線非 ISO，fromisoformat 會拒
    assert "無法解析" in out


# ── run_tool dispatch ──────────────────────────────────────────


async def test_run_tool_routes_get_schedule(db, monkeypatch):
    _freeze(monkeypatch, _local(2026, 6, 5, 11))
    out = await run_tool(db, "get_schedule", {})
    assert "行程" in out.text
    assert out.changed is None  # 唯讀工具不標改動


async def test_run_tool_routes_find_free_slots(db, monkeypatch):
    _freeze(monkeypatch, _local(2026, 6, 5, 8))
    out = await run_tool(db, "find_free_slots", {"min_minutes": 30})
    assert "空檔" in out.text or "沒有達" in out.text
    assert out.changed is None


async def test_run_tool_unknown_name(db):
    out = await run_tool(db, "delete_everything", {})
    assert out.text == "未知的工具：delete_everything"
    assert out.changed is None
