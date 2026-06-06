from datetime import datetime, timezone
from typing import Annotated

from pydantic import AfterValidator


def _ensure_utc(v: datetime) -> datetime:
    """把 naive datetime 視為 UTC，aware 的轉成 UTC。

    與 models.base.UTCDateTime 一致：API 邊界一律收斂成 UTC aware，
    避免後續和 DB 取回的 aware 值比較時炸出 TypeError。
    """
    if v.tzinfo is None:
        return v.replace(tzinfo=timezone.utc)
    return v.astimezone(timezone.utc)


# 用在 schema 的 datetime 欄位。Optional 欄位寫成 `UTCDatetime | None`，
# 值為 None 時走 None 分支、不會套用 validator。
UTCDatetime = Annotated[datetime, AfterValidator(_ensure_utc)]
