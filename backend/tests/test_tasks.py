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
