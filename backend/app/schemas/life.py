from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import EventCategory

# 預期壽命的合理區間；超出一律 422（schema 層擋掉，不進 DB）。
MIN_LIFE_EXPECTANCY = 1
MAX_LIFE_EXPECTANCY = 150
DEFAULT_LIFE_EXPECTANCY = 80


class LifeProfileWrite(BaseModel):
    """設定／更新人生倒數基準。生日的合理性（不能是未來）由 service 依 app 時區判定。"""

    birthday: date
    life_expectancy: int = Field(
        default=DEFAULT_LIFE_EXPECTANCY,
        ge=MIN_LIFE_EXPECTANCY,
        le=MAX_LIFE_EXPECTANCY,
    )


class LifeStats(BaseModel):
    """由生日＋預期壽命推導的倒數數字，全部以 app 時區的「今天」為基準。"""

    today: date
    end_date: date
    """預期終點：生日加上 life_expectancy 年。"""

    age: int
    total_days: int
    lived_days: int
    remaining_days: int
    percent_lived: float
    """已過比例（0–100，取到小數一位）。已超過預期壽命則為 100。"""

    lived_weeks: int
    remaining_weeks: int
    remaining_years: int
    days_left_this_year: int
    days_left_this_month: int
    next_birthday_in_days: int
    """距離下次生日的天數；今天就是生日時為 0。"""


class MilestoneRead(BaseModel):
    """標為 is_milestone 的未來行程，附上倒數天數。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    start_at: datetime
    target_date: date
    """行程在 app 時區的日期——倒數以「日」為單位，跟時分無關。"""

    days_left: int
    """距今天還有幾天；當天為 0。"""

    created_date: date
    """這筆行程被建立的日期（events.created_at），作為進度的起算點。"""

    total_days: int
    """從建立日到目標日的總天數（進度的分母）。同日建立且同日到期時為 0。"""

    elapsed_days: int
    """從建立日到今天已過的天數（進度的分子）。"""

    percent_elapsed: float
    """已走完的比例（0–100，小數一位）。分母為 0 時視為 100。"""

    age_at: int | None = None
    """屆時的歲數；尚未設定生日則為 null。"""

    category: EventCategory
    location: str | None = None
    note: str | None = None


class LifeRead(BaseModel):
    """尚未設定生日時 birthday/stats 為 null，前端據此顯示設定表單。

    milestones 與生日無關：沒設定生日也照樣列出（只是 age_at 為 null）。
    """

    model_config = ConfigDict(from_attributes=True)

    birthday: date | None = None
    life_expectancy: int = DEFAULT_LIFE_EXPECTANCY
    stats: LifeStats | None = None
    milestones: list[MilestoneRead] = Field(default_factory=list)
