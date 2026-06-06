from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.scheduling import detect_conflicts, find_free_slots

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
