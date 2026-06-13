"""推播排程器 process_due 的到點邏輯：該推的推、過期的只標記、沒收件人就不動。

不打真 LINE：client.push 換成記錄器。用固定 now 餵入，避免依賴系統時鐘。
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.chat import Conversation
from app.models.event import Event
from app.models.reminder import Reminder
from app.services import notifier

pytestmark = pytest.mark.asyncio

_NOW = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)


def _settings(push_user_id="", lead=10):
    return SimpleNamespace(
        line_push_user_id=push_user_id,
        line_channel_access_token="tok",
        event_reminder_lead_min=lead,
    )


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    """每個測試都把 get_settings 與 client.push 換掉；pushed 收集送出的訊息。"""
    monkeypatch.setattr(notifier, "get_settings", lambda: _settings())
    pushed = []

    async def fake_push(token, user_id, text):
        pushed.append((user_id, text))
        return True

    monkeypatch.setattr(notifier.client, "push", fake_push)
    return pushed


async def _convo_with_line(db, user_id="Uabc"):
    convo = Conversation(title="Aria", line_user_id=user_id)
    db.add(convo)
    await db.commit()
    return convo


async def test_due_reminder_is_pushed_and_marked(db, _patch):
    await _convo_with_line(db)
    r = Reminder(title="吃藥", subtitle="早晨例行", trigger_at=_NOW - timedelta(minutes=1), enabled=True)
    db.add(r)
    await db.commit()

    sent = await notifier.process_due(db, now=_NOW)

    assert len(sent) == 1
    assert "吃藥" in _patch[0][1]
    await db.refresh(r)
    assert r.fired_at == _NOW  # 已標記，下輪不再推


async def test_stale_reminder_marked_but_not_pushed(db, _patch):
    await _convo_with_line(db)
    r = Reminder(title="昨天的提醒", trigger_at=_NOW - timedelta(hours=2), enabled=True)
    db.add(r)
    await db.commit()

    sent = await notifier.process_due(db, now=_NOW)

    assert sent == []  # 過期不洗版
    await db.refresh(r)
    assert r.fired_at == _NOW  # 但仍標記，免得每輪重判


async def test_disabled_reminder_ignored(db, _patch):
    await _convo_with_line(db)
    r = Reminder(title="關掉的", trigger_at=_NOW - timedelta(minutes=1), enabled=False)
    db.add(r)
    await db.commit()

    sent = await notifier.process_due(db, now=_NOW)

    assert sent == []
    await db.refresh(r)
    assert r.fired_at is None  # 沒被碰


async def test_no_target_does_nothing(db, monkeypatch, _patch):
    # 沒設定收件人、conversation 也沒 line_user_id → 不推、不標記，等之後接上 LINE 再處理
    convo = Conversation(title="Aria", line_user_id=None)
    db.add(convo)
    r = Reminder(title="吃藥", trigger_at=_NOW - timedelta(minutes=1), enabled=True)
    db.add(r)
    await db.commit()

    sent = await notifier.process_due(db, now=_NOW)

    assert sent == []
    await db.refresh(r)
    assert r.fired_at is None


async def test_event_in_lead_window_pushed(db, _patch):
    await _convo_with_line(db)
    e = Event(
        title="設計週會",
        start_at=_NOW + timedelta(minutes=5),
        end_at=_NOW + timedelta(minutes=35),
    )
    db.add(e)
    await db.commit()

    sent = await notifier.process_due(db, now=_NOW)

    assert len(sent) == 1
    assert "設計週會" in _patch[0][1]
    await db.refresh(e)
    assert e.notified_at == _NOW


async def test_event_beyond_lead_not_touched(db, _patch):
    await _convo_with_line(db)
    e = Event(
        title="下午的會",
        start_at=_NOW + timedelta(minutes=30),  # 超出 lead=10 分鐘
        end_at=_NOW + timedelta(minutes=60),
    )
    db.add(e)
    await db.commit()

    sent = await notifier.process_due(db, now=_NOW)

    assert sent == []
    await db.refresh(e)
    assert e.notified_at is None


async def test_already_started_event_marked_not_pushed(db, _patch):
    await _convo_with_line(db)
    e = Event(
        title="已開始",
        start_at=_NOW - timedelta(minutes=3),  # 已開始但仍在 STALE 視窗內
        end_at=_NOW + timedelta(minutes=27),
    )
    db.add(e)
    await db.commit()

    sent = await notifier.process_due(db, now=_NOW)

    assert sent == []  # 不推馬後砲
    await db.refresh(e)
    assert e.notified_at == _NOW  # 但標記，免重判


async def test_due_reminder_not_marked_when_push_fails(db, monkeypatch):
    # 關鍵迴歸：到點提醒推播失敗時「不可」標記 fired_at，否則會被永久靜默丟掉；下輪要能重試。
    monkeypatch.setattr(notifier, "get_settings", lambda: _settings())

    async def failing_push(token, user_id, text):
        return False  # LINE 暫時性失敗

    monkeypatch.setattr(notifier.client, "push", failing_push)

    await _convo_with_line(db)
    r = Reminder(title="吃藥", trigger_at=_NOW - timedelta(minutes=1), enabled=True)
    db.add(r)
    await db.commit()

    sent = await notifier.process_due(db, now=_NOW)

    assert sent == []
    await db.refresh(r)
    assert r.fired_at is None  # 未標記 → 下輪會重試


async def test_due_event_not_marked_when_push_fails(db, monkeypatch):
    monkeypatch.setattr(notifier, "get_settings", lambda: _settings())

    async def failing_push(token, user_id, text):
        return False

    monkeypatch.setattr(notifier.client, "push", failing_push)

    await _convo_with_line(db)
    e = Event(
        title="設計週會",
        start_at=_NOW + timedelta(minutes=5),
        end_at=_NOW + timedelta(minutes=35),
    )
    db.add(e)
    await db.commit()

    await notifier.process_due(db, now=_NOW)

    await db.refresh(e)
    assert e.notified_at is None  # 即將開始但推播失敗 → 不標記，下輪重試


async def test_uses_configured_push_user_over_conversation(db, monkeypatch, _patch):
    # 設定釘死收件人時，優先於 conversation 捕捉到的 user
    monkeypatch.setattr(notifier, "get_settings", lambda: _settings(push_user_id="Ufixed"))
    await _convo_with_line(db, user_id="Ucaptured")
    db.add(Reminder(title="吃藥", trigger_at=_NOW - timedelta(minutes=1), enabled=True))
    await db.commit()

    await notifier.process_due(db, now=_NOW)

    assert _patch[0][0] == "Ufixed"
