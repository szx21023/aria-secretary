"""網頁登入驗證：單一密碼換 Bearer JWT，保護 /api/* 的唯讀與寫入路由。

單人自用設計——一個登入密碼（APP_PASSWORD）+ 一把簽章密鑰（AUTH_SECRET），兩者皆從環境變數注入。
登入成功簽發 HS256 JWT（帶 exp）；其餘 /api/* 路由掛 require_auth 驗 Authorization: Bearer。
LINE webhook 不走這裡（它自帶簽章＋白名單）；/api/health 與本檔的 /api/auth/login 維持公開。

Fail closed：APP_PASSWORD 或 AUTH_SECRET 未設定時，登入回 503、受保護路由一律 401——
寧可全鎖也不要在設定缺漏時悄悄全開（那正是這次要修掉的洞）。
"""

import hmac
import logging
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_ALGO = "HS256"
# auto_error=False：缺 header 時不由 HTTPBearer 自己回 403，改由 require_auth 統一回 401，
# 讓前端只需處理單一「401＝去登入」的訊號。
_bearer = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    password: str


class TokenResponse(BaseModel):
    token: str
    token_type: str = "bearer"


def _issue_token(secret: str, days: int) -> str:
    now = datetime.now(UTC)
    payload = {"sub": "owner", "iat": now, "exp": now + timedelta(days=days)}
    return jwt.encode(payload, secret, algorithm=_ALGO)


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest) -> TokenResponse:
    settings = get_settings()
    if not settings.app_password or not settings.auth_secret:
        logger.error("登入被呼叫但 APP_PASSWORD/AUTH_SECRET 未設定，無法簽發 token")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "登入功能尚未設定")
    # 密碼限 ASCII（不接受中文/emoji）。非 ASCII 一律當密碼錯誤，
    # 同時避免 hmac.compare_digest 收到非 ASCII str 丟 TypeError → 500。
    if not settings.app_password.isascii():
        logger.error("APP_PASSWORD 含非 ASCII 字元，無法比對；請改用純 ASCII 密碼")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "登入功能尚未正確設定")
    # 常數時間比較，避免以回應時間差側錄密碼長度／前綴
    if not req.password.isascii() or not hmac.compare_digest(req.password, settings.app_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "密碼錯誤")
    return TokenResponse(token=_issue_token(settings.auth_secret, settings.auth_token_days))


async def require_auth(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> str:
    """驗 Authorization: Bearer。通過回 token 的 sub；否則一律 401（含未設定密鑰時的 fail closed）。"""
    settings = get_settings()
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "需要登入", headers={"WWW-Authenticate": "Bearer"})
    if not settings.auth_secret:
        # 沒有密鑰就無法驗證任何 token → 一律擋，不放行。記一筆，否則整片 401
        # 會被誤判成「大家剛好都過期」，而非「AUTH_SECRET 掉了」這個設定問題。
        logger.error("require_auth 被呼叫但 AUTH_SECRET 未設定，fail-closed 全擋")
        raise unauthorized
    if creds is None or creds.scheme.lower() != "bearer":
        raise unauthorized
    try:
        payload = jwt.decode(creds.credentials, settings.auth_secret, algorithms=[_ALGO])
    except jwt.ExpiredSignatureError:
        # 過期是常態，使用者重新登入即可
        logger.info("token 過期，要求重新登入")
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "登入已失效，請重新登入", headers={"WWW-Authenticate": "Bearer"}
        ) from None
    except jwt.PyJWTError:
        # 簽章不符／格式錯——可能是換金鑰或偽造 token，比單純過期更值得注意
        logger.warning("token 驗證失敗（簽章或格式），要求重新登入")
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "登入已失效，請重新登入", headers={"WWW-Authenticate": "Bearer"}
        ) from None
    return payload.get("sub", "owner")
