"""里程碑：events.is_milestone 標記、/api/life 的 milestones 區塊、三個 AI 工具。

倒數以「app 時區的日期」為單位：當天的里程碑整天都該看得見（剩 0 天），
不因時間過了就消失；隔天才掉出清單。
"""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.executor import _TZ, create_milestone, get_milestones, run_tool, set_milestone
from app.models.event import Event
from app.services.life import list_milestones, today_local, upsert_profile


def _local(y, m, d, hh=9, mm=0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=_TZ).astimezone(UTC)


def _day_offset(days: int, hh: int = 9) -> datetime:
    """相對今天（在地）第 N 天的在地時刻，轉 UTC。測試不寫死日期，避免哪天就過期。"""
    d = today_local() + timedelta(days=days)
    return datetime(d.year, d.month, d.day, hh, tzinfo=_TZ).astimezone(UTC)


async def _add_event(db: AsyncSession, title: str, start: datetime, is_milestone: bool = False) -> Event:
    ev = Event(title=title, start_at=start, end_at=start + timedelta(hours=1), is_milestone=is_milestone)
    db.add(ev)
    await db.commit()
    await db.refresh(ev)
    return ev


# ---- events API 帶得動 is_milestone ----------------------------------------


async def test_event_defaults_to_not_milestone(client: AsyncClient):
    r = await client.post(
        "/api/events",
        json={"title": "每週同步", "start_at": "2027-06-07T15:00", "end_at": "2027-06-07T16:00"},
    )
    assert r.status_code == 201
    assert r.json()["is_milestone"] is False


async def test_event_can_be_created_and_toggled_as_milestone(client: AsyncClient):
    created = (
        await client.post(
            "/api/events",
            json={
                "title": "拿到 PMP 證照",
                "start_at": "2027-05-01T09:00",
                "end_at": "2027-05-01T10:00",
                "is_milestone": True,
            },
        )
    ).json()
    assert created["is_milestone"] is True

    r = await client.patch(f"/api/events/{created['id']}", json={"is_milestone": False})
    assert r.status_code == 200
    assert r.json()["is_milestone"] is False


async def test_patch_null_is_milestone_is_422(client: AsyncClient):
    created = (
        await client.post(
            "/api/events",
            json={"title": "x", "start_at": "2027-06-07T15:00", "end_at": "2027-06-07T16:00"},
        )
    ).json()
    r = await client.patch(f"/api/events/{created['id']}", json={"is_milestone": None})
    assert r.status_code == 422


# ---- /api/life 的 milestones ----------------------------------------------


async def test_life_lists_only_future_milestones(client: AsyncClient, db: AsyncSession):
    # 走 API 建資料，才會落在 client 用的那個 DB
    async def post(title, start, is_milestone):
        return await client.post(
            "/api/events",
            json={
                "title": title,
                "start_at": start.isoformat(),
                "end_at": (start + timedelta(hours=1)).isoformat(),
                "is_milestone": is_milestone,
            },
        )

    await post("已過去的里程碑", _day_offset(-3), True)
    await post("今天的里程碑", _day_offset(0), True)
    await post("未來的里程碑", _day_offset(30), True)
    await post("普通會議", _day_offset(1), False)

    body = (await client.get("/api/life")).json()
    titles = [m["title"] for m in body["milestones"]]
    assert titles == ["今天的里程碑", "未來的里程碑"]  # 由近到遠，過去的與非里程碑都不列
    assert body["milestones"][0]["days_left"] == 0
    assert body["milestones"][1]["days_left"] == 30


async def test_milestones_present_without_birthday(client: AsyncClient):
    await client.post(
        "/api/events",
        json={
            "title": "搬新家",
            "start_at": _day_offset(10).isoformat(),
            "end_at": (_day_offset(10) + timedelta(hours=1)).isoformat(),
            "is_milestone": True,
        },
    )
    body = (await client.get("/api/life")).json()
    assert body["birthday"] is None and body["stats"] is None
    assert len(body["milestones"]) == 1
    assert body["milestones"][0]["age_at"] is None  # 沒生日就沒歲數


async def test_age_at_filled_when_birthday_set(client: AsyncClient):
    await client.put("/api/life", json={"birthday": "1990-03-14", "life_expectancy": 80})
    await client.post(
        "/api/events",
        json={
            "title": "四十歲生日旅行",
            "start_at": "2030-03-20T09:00",
            "end_at": "2030-03-20T10:00",
            "is_milestone": True,
        },
    )
    body = (await client.get("/api/life")).json()
    assert body["milestones"][0]["age_at"] == 40


async def test_progress_denominator_is_target_minus_created(db: AsyncSession):
    """分母＝目標日−建立日；分子＝今天−建立日。剛建立時為 0%。"""
    await _add_event(db, "百日目標", _day_offset(100), is_milestone=True)
    m = (await list_milestones(db, None))[0]
    assert m.created_date == today_local()  # 剛建立
    assert m.total_days == 100
    assert m.elapsed_days == 0
    assert m.percent_elapsed == 0.0
    assert m.days_left == 100


async def test_progress_advances_as_created_date_recedes(db: AsyncSession):
    ev = await _add_event(db, "已走一半", _day_offset(50), is_milestone=True)
    # 把建立日往前挪 50 天：總長 100 天、已走 50 天
    ev.created_at = ev.created_at - timedelta(days=50)
    await db.commit()

    m = (await list_milestones(db, None))[0]
    assert m.total_days == 100
    assert m.elapsed_days == 50
    assert m.percent_elapsed == 50.0


async def test_progress_when_created_on_or_after_target(db: AsyncSession):
    """當天補記當天到期的目標：分母為 0，視為 100% 而非除以零。"""
    await _add_event(db, "今天就到期", _day_offset(0), is_milestone=True)
    m = (await list_milestones(db, None))[0]
    assert m.total_days == 0
    assert m.percent_elapsed == 100.0
    assert m.days_left == 0


async def test_list_milestones_ordered_and_capped(db: AsyncSession):
    for i in (30, 5, 100):
        await _add_event(db, f"m{i}", _day_offset(i), is_milestone=True)
    items = await list_milestones(db, None)
    assert [m.title for m in items] == ["m5", "m30", "m100"]


# ---- AI 工具 ---------------------------------------------------------------


async def test_get_milestones_empty(db: AsyncSession):
    assert "沒有標記任何人生里程碑" in await get_milestones(db)


async def test_get_milestones_lists_with_age(db: AsyncSession):
    await upsert_profile(db, datetime(1990, 3, 14).date(), 80)
    await _add_event(db, "去冰島看極光", _local(2030, 2, 14), is_milestone=True)
    text = await get_milestones(db)
    assert "去冰島看極光" in text
    assert "屆時 39 歲" in text
    assert "[id=" in text  # 帶 id，模型才能接著改期／取消


async def test_create_milestone_defaults_to_9am_hour_block(db: AsyncSession):
    res = await create_milestone(db, "考完證照", "2027-05-01")
    assert res.changed == "events"
    ev = await db.scalar(select(Event).where(Event.title == "考完證照"))
    assert ev.is_milestone is True
    local_start = ev.start_at.astimezone(_TZ)
    assert (local_start.hour, local_start.minute) == (9, 0)
    assert ev.end_at - ev.start_at == timedelta(hours=1)


async def test_create_milestone_honours_explicit_time_and_note(db: AsyncSession):
    await create_milestone(db, "婚禮", "2027-11-11", start_time="14:30", note="台北")
    ev = await db.scalar(select(Event).where(Event.title == "婚禮"))
    assert ev.start_at.astimezone(_TZ).strftime("%H:%M") == "14:30"
    assert ev.note == "台北"


async def test_create_milestone_bad_input_is_friendly(db: AsyncSession):
    bad_date = await create_milestone(db, "x", "明年五月")
    assert bad_date.changed is None and "無法解析" in bad_date.text

    bad_time = await create_milestone(db, "x", "2027-05-01", start_time="早上九點")
    assert bad_time.changed is None and "無法解析" in bad_time.text


async def test_create_milestone_rejects_past_date(db: AsyncSession):
    """人生頁只列今天之後的，過去日期若照建會回報成功卻查無此項——當場擋下。"""
    past = (today_local() - timedelta(days=1)).isoformat()
    res = await create_milestone(db, "上個月搬家", past)
    assert res.changed is None
    assert "已經過去了" in res.text
    assert await db.scalar(select(Event).where(Event.title == "上個月搬家")) is None


async def test_create_milestone_allows_today(db: AsyncSession):
    res = await create_milestone(db, "今天到期", today_local().isoformat())
    assert res.changed == "events"
    assert "就是今天" in res.text


async def test_create_milestone_ignores_conflicts(db: AsyncSession):
    """里程碑多是全天性質的目標，與當天既有行程重疊是常態，不該被衝突擋下。"""
    await _add_event(db, "既有會議", _local(2027, 5, 1, 9))
    res = await create_milestone(db, "考完證照", "2027-05-01")
    assert res.changed == "events"


async def test_set_milestone_marks_and_unmarks(db: AsyncSession):
    ev = await _add_event(db, "產品發表會", _day_offset(20))

    on = await set_milestone(db, "發表會", True)
    assert on.changed == "events"
    await db.refresh(ev)
    assert ev.is_milestone is True

    off = await set_milestone(db, "發表會", False)
    assert off.changed == "events"
    await db.refresh(ev)
    assert ev.is_milestone is False
    assert "行程保留" in off.text  # 說清楚沒刪行程，避免使用者誤會


async def test_set_milestone_no_op_when_already_in_state(db: AsyncSession):
    await _add_event(db, "婚禮", _day_offset(60), is_milestone=True)
    res = await set_milestone(db, "婚禮", True)
    assert res.changed is None
    assert "已經是里程碑" in res.text


async def test_set_milestone_not_found_and_ambiguous(db: AsyncSession):
    missing = await set_milestone(db, "不存在的東西", True)
    assert missing.changed is None and "找不到" in missing.text

    await _add_event(db, "體檢 A", _day_offset(3))
    await _add_event(db, "體檢 B", _day_offset(4))
    ambiguous = await set_milestone(db, "體檢", True)
    assert ambiguous.changed is None and "請確認" in ambiguous.text


async def test_run_tool_dispatches_milestone_tools(db: AsyncSession):
    created = await run_tool(db, "create_milestone", {"title": "搬家", "target_date": "2027-08-01"})
    assert created.changed == "events"
    assert "搬家" in (await run_tool(db, "get_milestones", {})).text
    toggled = await run_tool(db, "set_milestone", {"query": "搬家", "is_milestone": False})
    assert toggled.changed == "events"
