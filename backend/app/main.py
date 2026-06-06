from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import events, reminders, tasks
from app.config import get_settings
from app.db import AsyncSessionLocal, init_db
from app.seed import seed_if_empty

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with AsyncSessionLocal() as db:
        await seed_if_empty(db)
    yield


app = FastAPI(title="Aria · 私人秘書 API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(events.router)
app.include_router(tasks.router)
app.include_router(reminders.router)


@app.get("/api/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok", "app": "aria-secretary"}
