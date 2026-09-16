"""Notion 查詢：以關鍵字全文搜尋整個 workspace，整理成文字給模型閱讀。

用 httpx 直打官方 API（/v1/search），不引 notion SDK——同 weather / line 的取向。
只做唯讀搜尋；日後要加寫入（建頁/更新）時，本模組再加對應函式、executor 比照掛上。

回傳「給模型讀的文字」而非結構：未設定 token、查無結果、網路例外都轉成一句話回報，
讓 agent 能照實告訴使用者，而不是把例外往 chat loop 外炸（對齊 weather 的錯誤契約）。
Notion 整合只看得到「被分享給它」的頁面——查無結果可能是關鍵字不符，也可能是那頁沒分享。
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_TZ = ZoneInfo(get_settings().app_tz)

_SEARCH_URL = "https://api.notion.com/v1/search"
# Notion API 要求帶版本標頭；此為官方穩定版本字串。
_NOTION_VERSION = "2022-06-28"
_TIMEOUT = 10.0
# 一次回幾筆——夠回答「有沒有記過 X」，又不塞爆模型上下文。
_PAGE_SIZE = 8


def _extract_title(result: dict) -> str:
    """從 search 結果取標題純文字。

    page：標題藏在 properties 中 type == "title" 的那個屬性（名稱不定，需遍歷）。
    database：標題在頂層 title 陣列。兩者都是 rich_text 結構，取 plain_text 串接。
    取不到（無標題/結構非預期）回「（無標題）」，不讓呼叫端炸。
    """
    if result.get("object") == "database":
        rich = result.get("title") or []
    else:
        title_prop = next(
            (prop for prop in (result.get("properties") or {}).values() if prop.get("type") == "title"),
            None,
        )
        rich = (title_prop or {}).get("title") or []
    text = "".join(part.get("plain_text", "") for part in rich).strip()
    return text or "（無標題）"


def _format_edited(iso: str | None) -> str:
    """把 Notion 的 last_edited_time（ISO8601 UTC）轉本地時區後簡化成日期；解析不了就原樣回。

    轉 _TZ 再取日期：否則跨 UTC 午夜的編輯會顯示成前一天，與 app 其他地方（皆以在地時間顯示）不一致。
    """
    if not iso:
        return "時間不明"
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(_TZ).strftime("%Y-%m-%d")
    except ValueError:
        return iso


async def search_notion(query: str) -> str:
    """以關鍵字搜尋 Notion workspace，回傳符合的頁面/資料庫清單（給模型閱讀的文字）。

    Args:
        query: 搜尋關鍵字；空字串會被 Notion 當成「列出全部」，此處擋掉要求提供關鍵字。
    Returns:
        多行文字：每筆一行含類型、標題、最後編輯日、連結；查無或失敗回一句說明。
    """
    if not query or not query.strip():
        return "請提供要在 Notion 搜尋的關鍵字。"

    settings = get_settings()
    if not settings.notion_enabled:
        return "尚未設定 Notion 整合（NOTION_API_KEY），無法查詢 Notion。"

    headers = {
        "Authorization": f"Bearer {settings.notion_api_key}",
        "Notion-Version": _NOTION_VERSION,
        "Content-Type": "application/json",
    }
    payload = {
        "query": query,
        "page_size": _PAGE_SIZE,
        # 最近編輯的優先——問「有沒有記過 X」時，新的通常更相關。
        "sort": {"direction": "descending", "timestamp": "last_edited_time"},
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as http:
            response = await http.post(_SEARCH_URL, headers=headers, json=payload)
    except Exception:
        logger.exception("Notion 搜尋請求例外 query=%s", query)
        return "Notion 服務暫時無法連線，請稍後再試。"

    if response.status_code == 401:
        # token 失效／被撤銷——設定問題，明講讓使用者去修，別誤導成「查無資料」。
        logger.warning("Notion 搜尋 401：token 無效或已撤銷")
        return "Notion 認證失敗（token 無效或已撤銷），請檢查 NOTION_API_KEY。"
    if response.status_code // 100 != 2:
        logger.warning("Notion 搜尋 status=%s body=%s", response.status_code, response.text[:300])
        return "Notion 查詢失敗，請稍後再試。"

    try:
        body = response.json()
    except Exception:
        logger.warning("Notion 搜尋回應非預期 JSON")
        return "Notion 回應格式異常，請稍後再試。"
    results = body.get("results") or []
    # has_more：符合的比 page_size 多，只回了前幾筆。不講清楚會讓「找到 N 筆」被當成全部，
    # 對「以真實資料為準」的秘書是失真——寧可說「至少／還有更多」讓它照實轉述。
    has_more = bool(body.get("has_more"))

    if not results:
        # 查無可能是關鍵字不符，也可能是相關頁面沒分享給 integration——一併提示。
        return f"在 Notion 找不到與「{query}」相關的頁面（也可能是該頁尚未分享給整合）。"

    if has_more:
        header = f"Notion 搜尋「{query}」符合的項目較多，以下是最近編輯的前 {len(results)} 筆（可能還有更多）："
    else:
        header = f"Notion 搜尋「{query}」找到 {len(results)} 筆："
    lines = [header]
    for result in results:
        kind = "資料庫" if result.get("object") == "database" else "頁面"
        title = _extract_title(result)
        edited = _format_edited(result.get("last_edited_time"))
        url = result.get("url") or ""
        lines.append(f"- [{kind}] {title}（最後編輯 {edited}）{url}")
    return "\n".join(lines)
