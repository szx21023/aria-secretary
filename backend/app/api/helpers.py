from fastapi import HTTPException, status


def reject_null_fields(changes: dict, required: frozenset[str]) -> None:
    """部分更新時，擋掉「顯式送 null」到 NOT NULL 欄位的情況。

    *Update schema 的欄位型別是 `X | None`，client 可以顯式送 null。若直接寫進
    NOT NULL 欄位會在 commit 觸發 IntegrityError，被全域 handler 轉成 409 ——
    但這其實是請求格式錯誤，應該回 422 才對。這裡在進 DB 前先攔下來。
    """
    nulls = [k for k in required if k in changes and changes[k] is None]
    if nulls:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"欄位不可為 null：{', '.join(nulls)}",
        )
