"""Alembic 環境設定。

sqlalchemy.url 一律從 app settings 取得並轉成「同步」driver（Alembic 走同步），
所以本機/雲端只要設 DATABASE_URL 一處即可。一律開 batch mode：SQLite 的 ALTER 受限，
batch 會建暫存表搬資料；其他方言不受影響。
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import get_settings
from app.models import Base  # noqa: F401  — import 觸發所有 model 註冊到 metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _sync_url() -> str:
    """把 async driver 換成 Alembic 用的同步 driver。"""
    url = get_settings().database_url
    return url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg2")


def _render_item(type_, obj, autogen_context):
    """autogenerate 用到 app.models 的自訂型別（如 UTCDateTime）時，自動補上 import，
    否則產生的 migration 會 NameError。回 False＝其餘照預設 render。"""
    if type_ == "type" and obj.__class__.__module__.startswith("app.models"):
        autogen_context.imports.add(f"import {obj.__class__.__module__}")
    return False


def run_migrations_offline() -> None:
    context.configure(
        url=_sync_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _sync_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # 一律開：SQLite ALTER 受限，其他方言無副作用
            render_item=_render_item,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
