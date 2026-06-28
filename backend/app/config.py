from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """應用設定，從 .env / 環境變數載入。"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str = ""
    database_url: str = "sqlite+aiosqlite:///./aria.db"
    cors_origins: str = "http://localhost:5173"
    app_tz: str = "Asia/Taipei"
    # 啟動時 events 表為空是否灌入 demo 種子資料。dev 預設開（方便本機有資料可看）；
    # 接持久 DB（Cloud SQL）的正式環境設 false，避免清空行程後冷啟動又把 demo 種回來。
    seed_on_empty: bool = True

    # ── 網頁登入驗證 ──────────────────────────────────────────
    # 單人自用：一個登入密碼 + 一把 JWT 簽章密鑰，皆從環境變數注入。
    # 任一為空則 fail closed（登入回 503、受保護路由全 401）——正式環境務必設定。
    app_password: str = ""
    auth_secret: str = ""
    auth_token_days: int = 7  # 簽發 token 的有效天數

    # ── LINE 串接 ──────────────────────────────────────────────
    # 兩者皆有才視為啟用：缺任一就不掛 webhook、不啟動推播（純本機/網頁模式照常跑）。
    line_channel_secret: str = ""
    line_channel_access_token: str = ""
    # 推播目標。留空則用「最後一個跟 bot 講過話的人」（從 webhook 捕捉，存在 Conversation）。
    # 想釘死特定收件人時才填。
    line_push_user_id: str = ""
    # 對話授權白名單（逗號分隔的 LINE userId）。留空＝不限制（任何加到 bot 的人都能對話、
    # 並讀到主人的行程／歷史，啟動時會記一筆警告）；填了就只有名單內的人能用，其餘忽略並婉拒。
    line_allowed_user_ids: str = ""

    # ── 推播排程 ──────────────────────────────────────────────
    # 行程「即將開始」提前幾分鐘推；提醒則在 trigger_at 當下推。
    event_reminder_lead_min: int = 10
    # 背景排程器掃描間隔（秒）。設 0 可停用推播（仍保留 webhook 對話）。
    notifier_interval_sec: int = 60

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def line_enabled(self) -> bool:
        """secret 與 access token 都備齊才算啟用 LINE。"""
        return bool(self.line_channel_secret and self.line_channel_access_token)

    @property
    def line_allowed_user_id_list(self) -> list[str]:
        return [u.strip() for u in self.line_allowed_user_ids.split(",") if u.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
