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
    r = await client.post(
        "/api/events", json=_payload(end_at="2026-06-05T02:00:00Z")
    )
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
    r = await client.patch(
        f"/api/events/{created['id']}", json={"end_at": "2026-06-05T02:00:00Z"}
    )
    assert r.status_code == 422


async def test_delete_then_404(client: AsyncClient):
    created = (await client.post("/api/events", json=_payload())).json()
    assert (await client.delete(f"/api/events/{created['id']}")).status_code == 204
    assert (await client.get(f"/api/events/{created['id']}")).status_code == 404


async def test_get_missing_404(client: AsyncClient):
    assert (await client.get("/api/events/nope")).status_code == 404


async def test_list_filter_by_range(client: AsyncClient):
    await client.post("/api/events", json=_payload(title="今天", start_at="2026-06-05T02:00:00Z", end_at="2026-06-05T03:00:00Z"))
    await client.post("/api/events", json=_payload(title="明天", start_at="2026-06-06T02:00:00Z", end_at="2026-06-06T03:00:00Z"))

    r = await client.get("/api/events", params={"start": "2026-06-05T00:00:00Z", "end": "2026-06-06T00:00:00Z"})
    assert r.status_code == 200
    titles = [e["title"] for e in r.json()]
    assert titles == ["今天"]
