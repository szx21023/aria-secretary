from httpx import AsyncClient


async def test_create_defaults(client: AsyncClient):
    r = await client.post("/api/reminders", json={"title": "媽媽生日", "kind": "birthday"})
    assert r.status_code == 201
    body = r.json()
    assert body["enabled"] is True
    assert body["kind"] == "birthday"


async def test_toggle_enabled(client: AsyncClient):
    created = (await client.post("/api/reminders", json={"title": "帳單", "kind": "bill"})).json()
    r = await client.patch(f"/api/reminders/{created['id']}", json={"enabled": False})
    assert r.status_code == 200
    assert r.json()["enabled"] is False


async def test_delete_then_404(client: AsyncClient):
    created = (await client.post("/api/reminders", json={"title": "tmp", "kind": "health"})).json()
    assert (await client.delete(f"/api/reminders/{created['id']}")).status_code == 204
    assert (await client.get(f"/api/reminders/{created['id']}")).status_code == 404


async def test_missing_404(client: AsyncClient):
    assert (await client.get("/api/reminders/nope")).status_code == 404
    assert (await client.patch("/api/reminders/nope", json={"enabled": False})).status_code == 404
    assert (await client.delete("/api/reminders/nope")).status_code == 404
