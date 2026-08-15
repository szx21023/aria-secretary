from datetime import date

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.life import LifeProfile
from app.services.life import add_years, compute_stats, full_years_between, upsert_profile

# ---- API ----------------------------------------------------------------


async def test_get_before_setup_returns_nulls(client: AsyncClient):
    r = await client.get("/api/life")
    assert r.status_code == 200
    body = r.json()
    assert body["birthday"] is None
    assert body["stats"] is None
    assert body["life_expectancy"] == 80  # 預設值，讓前端表單有起始值


async def test_put_then_get_round_trips_with_stats(client: AsyncClient):
    r = await client.put("/api/life", json={"birthday": "1990-03-14", "life_expectancy": 80})
    assert r.status_code == 200
    assert r.json()["birthday"] == "1990-03-14"
    assert r.json()["stats"]["end_date"] == "2070-03-14"

    body = (await client.get("/api/life")).json()
    assert body["birthday"] == "1990-03-14"
    assert body["stats"]["total_days"] > 0
    # 不含今天的定義下，兩者相加恆等於總天數
    s = body["stats"]
    assert s["lived_days"] + s["remaining_days"] == s["total_days"]


async def test_put_defaults_life_expectancy(client: AsyncClient):
    r = await client.put("/api/life", json={"birthday": "2000-01-01"})
    assert r.status_code == 200
    assert r.json()["life_expectancy"] == 80


async def test_put_twice_updates_in_place(client: AsyncClient):
    # 連續兩次 PUT 應覆蓋同一筆（單列語意見 test_upsert_keeps_one_row）
    await client.put("/api/life", json={"birthday": "1990-03-14", "life_expectancy": 80})
    await client.put("/api/life", json={"birthday": "1991-04-15", "life_expectancy": 90})

    body = (await client.get("/api/life")).json()
    assert body["birthday"] == "1991-04-15"
    assert body["life_expectancy"] == 90
    assert body["stats"]["end_date"] == "2081-04-15"


async def test_future_birthday_is_422(client: AsyncClient):
    assert (await client.put("/api/life", json={"birthday": "2999-01-01"})).status_code == 422


async def test_life_expectancy_out_of_range_is_422(client: AsyncClient):
    for bad in (0, -1, 151):
        r = await client.put("/api/life", json={"birthday": "1990-03-14", "life_expectancy": bad})
        assert r.status_code == 422, bad


async def test_upsert_keeps_one_row(db: AsyncSession):
    await upsert_profile(db, date(1990, 3, 14), 80)
    await upsert_profile(db, date(1990, 3, 14), 85)
    count = await db.scalar(select(func.count()).select_from(LifeProfile))
    assert count == 1


# ---- 純日期推導 ----------------------------------------------------------


def test_stats_basic_math():
    s = compute_stats(date(1990, 3, 14), 80, today=date(2026, 8, 15))
    assert s.end_date == date(2070, 3, 14)
    assert s.age == 36
    assert s.lived_days == (date(2026, 8, 15) - date(1990, 3, 14)).days
    assert s.remaining_days == (date(2070, 3, 14) - date(2026, 8, 15)).days
    assert s.lived_days + s.remaining_days == s.total_days
    assert s.lived_weeks == s.lived_days // 7
    assert 0 < s.percent_lived < 100


def test_stats_past_life_expectancy_clamps():
    s = compute_stats(date(1900, 1, 1), 80, today=date(2026, 8, 15))
    assert s.remaining_days == 0
    assert s.remaining_weeks == 0
    assert s.remaining_years == 0
    assert s.percent_lived == 100.0


def test_days_left_this_year_and_month():
    s = compute_stats(date(1990, 3, 14), 80, today=date(2026, 12, 31))
    assert s.days_left_this_year == 0
    assert s.days_left_this_month == 0

    s = compute_stats(date(1990, 3, 14), 80, today=date(2026, 2, 1))
    assert s.days_left_this_month == 27  # 2026 非閏年，2 月 28 天


def test_leap_day_birthday_falls_back_to_28th():
    assert add_years(date(2000, 2, 29), 1) == date(2001, 2, 28)
    assert add_years(date(2000, 2, 29), 4) == date(2004, 2, 29)


def test_next_birthday_today_is_zero():
    s = compute_stats(date(1990, 3, 14), 80, today=date(2026, 3, 14))
    assert s.next_birthday_in_days == 0
    assert s.age == 36

    s = compute_stats(date(1990, 3, 14), 80, today=date(2026, 3, 15))
    assert s.next_birthday_in_days == (date(2027, 3, 14) - date(2026, 3, 15)).days


def test_full_years_between_edges():
    assert full_years_between(date(1990, 3, 14), date(1990, 3, 14)) == 0
    assert full_years_between(date(1990, 3, 14), date(1991, 3, 13)) == 0
    assert full_years_between(date(1990, 3, 14), date(1991, 3, 14)) == 1
    assert full_years_between(date(1991, 3, 14), date(1990, 3, 14)) == 0  # 反向不給負值


def test_not_yet_born_gives_zero_lived():
    s = compute_stats(date(2026, 9, 1), 80, today=date(2026, 8, 15))
    assert s.lived_days == 0
    assert s.age == 0
    assert s.percent_lived == 0.0
