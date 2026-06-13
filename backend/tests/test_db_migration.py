"""Alembic migration：upgrade head 建出的 schema 與 models 完全一致，且可重複執行。

取代了舊的手刻 _add_missing_columns。平時測試的 in-memory 庫走 Base.metadata.create_all，
這裡才實際走 Alembic 路徑（也是正式啟動 init_db 走的路徑）。
"""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from app.config import get_settings
from app.db import _upgrade_to_head
from app.models import Base


def _upgrade_temp(db_path) -> None:
    _upgrade_to_head()
    _upgrade_to_head()  # 已在 head → no-op，不可重跑就報錯（idempotent）


def test_baseline_matches_models_and_is_idempotent(tmp_path, monkeypatch):
    db = tmp_path / "migrate.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db}")
    get_settings.cache_clear()  # 讓 env.py 取到 temp DB
    try:
        _upgrade_temp(db)

        # 全表/欄位/索引/FK 與 models 零差異——比硬列幾個欄位強，migration drift 會被抓到
        engine = create_engine(f"sqlite:///{db}")
        try:
            with engine.connect() as conn:
                ctx = MigrationContext.configure(conn, opts={"render_as_batch": True})
                diffs = compare_metadata(ctx, Base.metadata)
        finally:
            engine.dispose()
    finally:
        get_settings.cache_clear()

    assert diffs == [], f"baseline migration 與 models 不同步: {diffs}"
