"""登入驗證：密碼換 token、受保護路由擋未授權、fail-closed（未設定密鑰即全鎖）。

用獨立的 auth_client fixture——刻意**不**覆寫 require_auth（與 conftest 的 client 不同），
才能驗到真實的把關；並 monkeypatch app.api.auth.get_settings 注入測試用密碼/密鑰。
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app import config
from app.db import get_db
from app.main import app
from app.models.base import Base

pytestmark = pytest.mark.asyncio

_PASSWORD = "s3cret-pw"  # pragma: allowlist secret  測試用假密碼
_SECRET = "test-signing-key"  # pragma: allowlist secret  測試用假密鑰


def _settings(**over) -> config.Settings:
    base = {"app_password": _PASSWORD, "auth_secret": _SECRET}
    base.update(over)
    return config.Settings(**base)


@pytest_asyncio.fixture
async def auth_client(monkeypatch):
    """auth 真實生效的 client（require_auth 不被覆寫）。可用 monkeypatch 換 settings。"""
    monkeypatch.setattr("app.api.auth.get_settings", _settings)

    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    test_session = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with test_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, monkeypatch
    app.dependency_overrides.clear()
    await engine.dispose()


async def test_login_wrong_password_401(auth_client):
    ac, _ = auth_client
    resp = await ac.post("/api/auth/login", json={"password": "nope"})  # pragma: allowlist secret
    assert resp.status_code == 401


async def test_login_correct_returns_token(auth_client):
    ac, _ = auth_client
    resp = await ac.post("/api/auth/login", json={"password": _PASSWORD})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token"] and body["token_type"] == "bearer"


async def test_protected_route_rejects_without_token(auth_client):
    ac, _ = auth_client
    resp = await ac.get("/api/tasks")
    assert resp.status_code == 401


async def test_protected_route_accepts_valid_token(auth_client):
    ac, _ = auth_client
    token = (await ac.post("/api/auth/login", json={"password": _PASSWORD})).json()["token"]
    resp = await ac.get("/api/tasks", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


async def test_protected_route_rejects_garbage_token(auth_client):
    ac, _ = auth_client
    resp = await ac.get("/api/tasks", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401


async def test_token_signed_with_other_secret_rejected(auth_client):
    ac, monkeypatch = auth_client
    # 用別把密鑰簽出來的 token，換回正確密鑰驗證 → 必須被拒（簽章不符）
    monkeypatch.setattr("app.api.auth.get_settings", lambda: _settings(auth_secret="attacker-key"))
    forged = (await ac.post("/api/auth/login", json={"password": _PASSWORD})).json()["token"]
    monkeypatch.setattr("app.api.auth.get_settings", _settings)
    resp = await ac.get("/api/tasks", headers={"Authorization": f"Bearer {forged}"})
    assert resp.status_code == 401


async def test_fail_closed_when_unconfigured(auth_client):
    ac, monkeypatch = auth_client
    # 未設定 APP_PASSWORD/AUTH_SECRET：登入回 503、受保護路由回 401（寧可全鎖不全開）
    monkeypatch.setattr("app.api.auth.get_settings", lambda: config.Settings(app_password="", auth_secret=""))
    login = await ac.post("/api/auth/login", json={"password": "anything"})  # pragma: allowlist secret
    assert login.status_code == 503
    protected = await ac.get("/api/tasks")
    assert protected.status_code == 401


async def test_line_webhook_not_behind_jwt(auth_client):
    ac, _ = auth_client
    # LINE webhook 不該被 JWT 擋（它自有簽章/白名單）；無 token 打過去不應是 401。
    resp = await ac.post("/api/line/webhook", json={})
    assert resp.status_code != 401
