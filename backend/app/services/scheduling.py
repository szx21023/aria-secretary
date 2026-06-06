"""排程相關的純函式：衝突偵測、找空檔。

刻意不碰 DB，只吃 Event 物件（或任何有 id/start_at/end_at 的東西），
方便單元測試，並讓 M3/M4 的 AI 工具直接重用同一套邏輯。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

# 「結束必須晚於開始」的共用錯誤訊息，給 schema 與 router 共用，避免兩處字串漂移。
INTERVAL_ERROR = "end_at 必須晚於 start_at"


def interval_ok(start_at: datetime, end_at: datetime) -> bool:
    """區間是否有效（end 嚴格晚於 start）。"""
    return end_at > start_at


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
    """回傳與 [start_at, end_at) 重疊的行程（依開始時間排序），排除 exclude_id 自己。

    傳入的目標區間若無效（end <= start）視為呼叫端錯誤，直接拋 ValueError，
    而非靜默回傳空陣列讓 bug 看起來像「沒有衝突」。
    """
    if not interval_ok(start_at, end_at):
        raise ValueError(INTERVAL_ERROR)
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

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError("FreeSlot 的 end 必須晚於 start")

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

    回傳的空檔同樣是半開區間，會緊貼下一個行程的開始（例如 09–10 接在 10:00 開始的行程前）。
    會自動忽略落在視窗外的行程、並處理彼此重疊的行程（取聯集後算間隙）。
    視窗反向（window_end < window_start）視為呼叫端錯誤而拋 ValueError；
    零寬視窗（相等）則合理地回傳空陣列。
    """
    if window_end < window_start:
        raise ValueError("window_end 不可早於 window_start")
    if window_end == window_start:
        return []

    min_delta = timedelta(minutes=min_minutes)

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
        if start - cursor >= min_delta:
            slots.append(FreeSlot(cursor, start))
        # 只在行程結束晚於游標時推進，避免「被完全包含的短行程」把游標往回拉而破壞聯集
        if end > cursor:
            cursor = end
    if window_end - cursor >= min_delta:
        slots.append(FreeSlot(cursor, window_end))

    return slots
