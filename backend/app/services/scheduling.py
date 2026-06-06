"""排程相關的純函式：衝突偵測、找空檔。

刻意不碰 DB，只吃 Event 物件（或任何有 id/start_at/end_at 的東西），
方便單元測試，並讓 M3/M4 的 AI 工具直接重用同一套邏輯。
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class HasInterval(Protocol):
    id: str
    start_at: datetime
    end_at: datetime


def _overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    # 半開區間 [start, end)，相接（a_end == b_start）不算衝突
    return a_start < b_end and b_start < a_end


def detect_conflicts(
    events: list[HasInterval],
    start_at: datetime,
    end_at: datetime,
    exclude_id: str | None = None,
) -> list[HasInterval]:
    """回傳與 [start_at, end_at) 重疊的行程（依開始時間排序），排除 exclude_id 自己。"""
    hits = [
        e
        for e in events
        if e.id != exclude_id and _overlaps(start_at, end_at, e.start_at, e.end_at)
    ]
    return sorted(hits, key=lambda e: e.start_at)


@dataclass(frozen=True)
class FreeSlot:
    start: datetime
    end: datetime

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


def find_free_slots(
    events: list[HasInterval],
    window_start: datetime,
    window_end: datetime,
    min_minutes: int = 30,
) -> list[FreeSlot]:
    """在 [window_start, window_end) 內，回傳長度 >= min_minutes 的空檔。

    會自動忽略落在視窗外的行程、並處理彼此重疊的行程（取聯集後算間隙）。
    """
    if window_end <= window_start:
        return []

    # 只看與視窗相交的行程，並把開始/結束夾到視窗內
    clipped: list[tuple[datetime, datetime]] = []
    for e in events:
        if e.end_at <= window_start or e.start_at >= window_end:
            continue
        clipped.append((max(e.start_at, window_start), min(e.end_at, window_end)))
    clipped.sort()

    slots: list[FreeSlot] = []
    cursor = window_start
    for start, end in clipped:
        if start - cursor >= _min(min_minutes):
            slots.append(FreeSlot(cursor, start))
        if end > cursor:
            cursor = end
    if window_end - cursor >= _min(min_minutes):
        slots.append(FreeSlot(cursor, window_end))

    return slots


def _min(minutes: int):
    from datetime import timedelta

    return timedelta(minutes=minutes)
