from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services.scheduling import FreeSlot, detect_conflicts, find_free_slots

UTC = timezone.utc


def _ev(eid: str, h0: int, h1: int) -> SimpleNamespace:
    day = datetime(2026, 6, 5, tzinfo=UTC)
    return SimpleNamespace(id=eid, start_at=day + timedelta(hours=h0), end_at=day + timedelta(hours=h1))


def test_detect_conflicts_finds_overlap():
    events = [_ev("a", 9, 10), _ev("b", 10, 11), _ev("c", 11, 12)]
    hits = detect_conflicts(events, _ev("x", 9, 10).start_at, _ev("x", 9, 11).end_at)
    assert {e.id for e in hits} == {"a", "b"}


def test_detect_conflicts_adjacent_is_not_conflict():
    events = [_ev("a", 9, 10)]
    # 10:00–11:00 緊接 a 的結束，不算衝突
    hits = detect_conflicts(events, _ev("x", 10, 11).start_at, _ev("x", 10, 11).end_at)
    assert hits == []


def test_detect_conflicts_excludes_self():
    target = _ev("a", 9, 10)
    hits = detect_conflicts([target], target.start_at, target.end_at, exclude_id="a")
    assert hits == []


def test_find_free_slots_basic():
    day = datetime(2026, 6, 5, tzinfo=UTC)
    window_start = day + timedelta(hours=9)
    window_end = day + timedelta(hours=18)
    events = [_ev("a", 10, 11), _ev("b", 13, 14)]
    slots = find_free_slots(events, window_start, window_end, min_minutes=30)
    # 9–10、11–13、14–18
    spans = [(s.start.hour, s.end.hour) for s in slots]
    assert spans == [(9, 10), (11, 13), (14, 18)]


def test_find_free_slots_respects_min_minutes():
    day = datetime(2026, 6, 5, tzinfo=UTC)
    window_start = day + timedelta(hours=9)
    window_end = day + timedelta(hours=12)
    # 9:00–9:20 的小空檔應被 min_minutes=30 過濾掉
    events = [_ev("a", 9, 9), _ev("packed", 9, 12)]
    events[0].end_at = window_start + timedelta(minutes=20)
    events[1].start_at = window_start + timedelta(minutes=20)
    slots = find_free_slots(events, window_start, window_end, min_minutes=30)
    assert slots == []


def test_find_free_slots_merges_overlapping_events():
    day = datetime(2026, 6, 5, tzinfo=UTC)
    window_start = day + timedelta(hours=9)
    window_end = day + timedelta(hours=15)
    events = [_ev("a", 10, 12), _ev("b", 11, 13)]  # 重疊 → 視為 10–13 被佔
    slots = find_free_slots(events, window_start, window_end, min_minutes=30)
    spans = [(s.start.hour, s.end.hour) for s in slots]
    assert spans == [(9, 10), (13, 15)]


def test_detect_conflicts_returns_sorted_list():
    # 故意亂序傳入，確認回傳依 start_at 排序（鎖住 docstring 承諾的契約）
    events = [_ev("late", 14, 15), _ev("early", 9, 10), _ev("mid", 11, 12)]
    hits = detect_conflicts(events, _ev("x", 9, 16).start_at, _ev("x", 9, 16).end_at)
    assert [e.id for e in hits] == ["early", "mid", "late"]


def test_detect_conflicts_rejects_inverted_interval():
    with pytest.raises(ValueError):
        detect_conflicts([], _ev("x", 11, 10).start_at, _ev("x", 11, 10).end_at)


def test_find_free_slots_empty_window_returns_empty():
    day = datetime(2026, 6, 5, tzinfo=UTC)
    t = day + timedelta(hours=9)
    assert find_free_slots([], t, t) == []  # 零寬視窗


def test_find_free_slots_inverted_window_raises():
    day = datetime(2026, 6, 5, tzinfo=UTC)
    with pytest.raises(ValueError):
        find_free_slots([], day + timedelta(hours=12), day + timedelta(hours=9))


def test_find_free_slots_no_events_is_whole_window():
    day = datetime(2026, 6, 5, tzinfo=UTC)
    ws, we = day + timedelta(hours=9), day + timedelta(hours=18)
    slots = find_free_slots([], ws, we, min_minutes=30)
    assert len(slots) == 1
    assert slots[0].start == ws and slots[0].end == we


def test_free_slot_minutes():
    day = datetime(2026, 6, 5, tzinfo=UTC)
    slot = FreeSlot(day + timedelta(hours=9), day + timedelta(hours=10, minutes=30))
    assert slot.minutes == 90


def test_free_slot_rejects_invalid():
    day = datetime(2026, 6, 5, tzinfo=UTC)
    with pytest.raises(ValueError):
        FreeSlot(day + timedelta(hours=10), day + timedelta(hours=9))
