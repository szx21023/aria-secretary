from httpx import AsyncClient


def _payload(**over) -> dict:
    base = {
        "title": "與設計團隊週會",
        "start_at": "2026-06-05T02:30:00Z",  # 10:30 台北
        "end_at": "2026-06-05T03:30:00Z",
        "category": "meeting",
        "location": "Google Meet",
        "attendees": 5,
    }
    base.update(over)
    return base


async def test_health(client: AsyncClient):
    r = await client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


async def test_create_and_get(client: AsyncClient):
    r = await client.post("/api/events", json=_payload())
    assert r.status_code == 201
    created = r.json()
    assert created["title"] == "與設計團隊週會"
    assert created["status"] == "scheduled"
    assert created["id"]

    r2 = await client.get(f"/api/events/{created['id']}")
    assert r2.status_code == 200
    assert r2.json()["attendees"] == 5


async def test_create_rejects_end_before_start(client: AsyncClient):
    r = await client.post("/api/events", json=_payload(end_at="2026-06-05T02:00:00Z"))
    assert r.status_code == 422


async def test_patch_reschedule(client: AsyncClient):
    created = (await client.post("/api/events", json=_payload())).json()
    r = await client.patch(
        f"/api/events/{created['id']}",
        json={
            "start_at": "2026-06-05T04:00:00Z",
            "end_at": "2026-06-05T05:00:00Z",
            "note": "已由秘書順延",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["note"] == "已由秘書順延"
    assert body["start_at"] == "2026-06-05T04:00:00Z"


async def test_patch_invalid_interval(client: AsyncClient):
    created = (await client.post("/api/events", json=_payload())).json()
    r = await client.patch(f"/api/events/{created['id']}", json={"end_at": "2026-06-05T02:00:00Z"})
    assert r.status_code == 422


async def test_delete_then_404(client: AsyncClient):
    created = (await client.post("/api/events", json=_payload())).json()
    assert (await client.delete(f"/api/events/{created['id']}")).status_code == 204
    assert (await client.get(f"/api/events/{created['id']}")).status_code == 404


async def test_get_missing_404(client: AsyncClient):
    assert (await client.get("/api/events/nope")).status_code == 404


async def test_list_filter_by_range(client: AsyncClient):
    await client.post(
        "/api/events",
        json=_payload(title="今天", start_at="2026-06-05T02:00:00Z", end_at="2026-06-05T03:00:00Z"),
    )
    await client.post(
        "/api/events",
        json=_payload(title="明天", start_at="2026-06-06T02:00:00Z", end_at="2026-06-06T03:00:00Z"),
    )

    r = await client.get("/api/events", params={"start": "2026-06-05T00:00:00Z", "end": "2026-06-06T00:00:00Z"})
    assert r.status_code == 200
    titles = [e["title"] for e in r.json()]
    assert titles == ["今天"]


async def test_create_rejects_end_equals_start(client: AsyncClient):
    # 邊界：end == start 應被拒（驗證用 <=，不是 <）
    r = await client.post("/api/events", json=_payload(end_at="2026-06-05T02:30:00Z"))
    assert r.status_code == 422


async def test_patch_null_datetime_rejected(client: AsyncClient):
    # 回歸測試：顯式送 null 以前會炸成 500
    created = (await client.post("/api/events", json=_payload())).json()
    r = await client.patch(f"/api/events/{created['id']}", json={"start_at": None})
    assert r.status_code == 422


async def test_patch_naive_datetime_coerced(client: AsyncClient):
    # 回歸測試：naive datetime 以前會在比較時炸成 500；現在當成 UTC
    created = (await client.post("/api/events", json=_payload())).json()
    r = await client.patch(f"/api/events/{created['id']}", json={"end_at": "2026-06-05T05:00:00"})
    assert r.status_code == 200
    assert r.json()["end_at"] == "2026-06-05T05:00:00Z"


async def test_patch_start_moved_past_end(client: AsyncClient):
    # 只改 start_at 到現有 end_at 之後 → 必須 422（跨欄位、合併後才驗得出）
    created = (await client.post("/api/events", json=_payload())).json()
    r = await client.patch(f"/api/events/{created['id']}", json={"start_at": "2026-06-05T04:00:00Z"})
    assert r.status_code == 422


async def test_patch_null_title_is_422_not_409(client: AsyncClient):
    # 顯式 null 到 NOT NULL 欄位是請求格式錯誤 → 422，不該被 IntegrityError handler 蓋成 409
    created = (await client.post("/api/events", json=_payload())).json()
    r = await client.patch(f"/api/events/{created['id']}", json={"title": None})
    assert r.status_code == 422


async def test_patch_missing_404(client: AsyncClient):
    assert (await client.patch("/api/events/nope", json={"title": "x"})).status_code == 404


async def test_delete_missing_404(client: AsyncClient):
    assert (await client.delete("/api/events/nope")).status_code == 404
