from httpx import AsyncClient


async def test_create_list_and_default_done_false(client: AsyncClient):
    r = await client.post("/api/tasks", json={"title": "回覆投資人月報信件", "priority": "high"})
    assert r.status_code == 201
    body = r.json()
    assert body["done"] is False
    assert body["priority"] == "high"

    listed = (await client.get("/api/tasks")).json()
    assert any(t["title"] == "回覆投資人月報信件" for t in listed)


async def test_toggle_done(client: AsyncClient):
    created = (await client.post("/api/tasks", json={"title": "整理筆記"})).json()
    r = await client.patch(f"/api/tasks/{created['id']}", json={"done": True})
    assert r.status_code == 200
    assert r.json()["done"] is True


async def test_get_task(client: AsyncClient):
    created = (await client.post("/api/tasks", json={"title": "查一下"})).json()
    r = await client.get(f"/api/tasks/{created['id']}")
    assert r.status_code == 200
    assert r.json()["title"] == "查一下"


async def test_delete_then_404(client: AsyncClient):
    created = (await client.post("/api/tasks", json={"title": "tmp"})).json()
    assert (await client.delete(f"/api/tasks/{created['id']}")).status_code == 204
    assert (await client.patch(f"/api/tasks/{created['id']}", json={"done": True})).status_code == 404


async def test_missing_404(client: AsyncClient):
    assert (await client.get("/api/tasks/nope")).status_code == 404
    assert (await client.patch("/api/tasks/nope", json={"done": True})).status_code == 404
    assert (await client.delete("/api/tasks/nope")).status_code == 404


async def test_patch_null_required_field_is_422(client: AsyncClient):
    created = (await client.post("/api/tasks", json={"title": "x"})).json()
    assert (await client.patch(f"/api/tasks/{created['id']}", json={"title": None})).status_code == 422
    assert (await client.patch(f"/api/tasks/{created['id']}", json={"done": None})).status_code == 422


async def test_naive_due_at_coerced_to_utc(client: AsyncClient):
    r = await client.post("/api/tasks", json={"title": "出差機票", "due_at": "2026-06-06T09:00:00"})
    assert r.status_code == 201
    assert r.json()["due_at"] == "2026-06-06T09:00:00Z"


async def test_null_due_at_round_trips(client: AsyncClient):
    # Optional 欄位顯式 null 應正常通過（走 None 分支、不套 UTC validator）
    r = await client.post("/api/tasks", json={"title": "無期限", "due_at": None})
    assert r.status_code == 201
    assert r.json()["due_at"] is None
