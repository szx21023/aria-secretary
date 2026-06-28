import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, chat, events, line, reminders, tasks
from app.api.auth import require_auth
from app.config import get_settings
from app.db import AsyncSessionLocal, init_db
from app.exception_handlers import register_exception_handlers
from app.seed import seed_if_empty
from app.services.conversation import get_or_create_conversation
from app.services.notifier import run_notifier

settings = get_settings()


def _setup_logging() -> None:
    """讓 app.* 的 INFO 日誌（工具呼叫、stream 警告）真的輸出。

    uvicorn 預設只配置自己的 logger，app logger 會落到 root 的 lastResort handler（WARNING 起跳），
    INFO 會被丟掉。這裡只把 "app" 命名空間獨立拉到 INFO，不動 root，避免 httpx/sqlalchemy 一起變吵。
    在 lifespan 啟動時呼叫（而非 import 時），才不會在被 import 的測試行程裡偷改全域 logging 狀態。
    """
    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False  # 設在 handler 判斷外，狀態才不依賴 import 次序
    if not app_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
        app_logger.addHandler(handler)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _setup_logging()
    await init_db()
    async with AsyncSessionLocal() as db:
        if settings.seed_on_empty:
            await seed_if_empty(db)
        # 啟動時先確保全域 conversation 存在，這樣 webhook 背景工作與推播排程器
        # 之後都只走 SELECT 分支，不會兩條路同時 INSERT 出兩個 conversation、
        # 把「網頁與 LINE 共用單一記憶」的前提拆掉。
        await get_or_create_conversation(db)

    # LINE 啟用但沒設白名單：任何加到 bot 的人都能對話、讀到主人的行程與歷史。
    # 不擋（單人 MVP 要能先加好友抓自己的 userId），但大聲記一筆。
    if settings.line_enabled and not settings.line_allowed_user_id_list:
        logging.getLogger("app").warning(
            "LINE bot 未設定 LINE_ALLOWED_USER_IDS，任何人都能與秘書對話並讀到你的行程；"
            "建議從 log 取得自己的 userId 後填入白名單。"
        )

    # LINE 啟用且推播未停用時，背景常駐排程器負責提醒/行程到點推播。
    notifier_task = None
    if settings.line_enabled and settings.notifier_interval_sec > 0:
        notifier_task = asyncio.create_task(run_notifier())

    yield

    if notifier_task is not None:
        notifier_task.cancel()
        try:
            await notifier_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Aria · 私人秘書 API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 資料與對話路由一律要登入（Bearer JWT）。LINE webhook 自帶簽章＋白名單、auth/login 為公開入口。
_protected = [Depends(require_auth)]
app.include_router(events.router, dependencies=_protected)
app.include_router(tasks.router, dependencies=_protected)
app.include_router(reminders.router, dependencies=_protected)
app.include_router(chat.router, dependencies=_protected)
app.include_router(line.router)
app.include_router(auth.router)

# 統一錯誤信封：HTTPException / 驗證錯誤 / IntegrityError / 未捕捉例外
register_exception_handlers(app)


@app.get("/api/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok", "app": "aria-secretary"}
