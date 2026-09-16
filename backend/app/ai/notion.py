"""Notion 查詢：搜尋 workspace、讀取單一頁面內容，整理成文字給模型閱讀。

用 httpx 直打官方 API（/v1/search、/v1/pages、/v1/blocks），不引 notion SDK——同 weather / line 的取向。
只做唯讀；日後要加寫入（建頁/更新）時，本模組再加對應函式、executor 比照掛上。
- search_notion：以關鍵字全文搜尋，回符合的頁面/資料庫清單（標題、最後編輯日、連結）。
- read_notion_page：拿 search 回傳的連結/ID，把該頁的 block 內容攤平成文字（含清單/待辦等巢狀）。

回傳「給模型讀的文字」而非結構：未設定 token、查無結果、網路例外都轉成一句話回報，
讓 agent 能照實告訴使用者，而不是把例外往 chat loop 外炸（對齊 weather 的錯誤契約）。
Notion 整合只看得到「被分享給它」的頁面——查無/讀不到可能是關鍵字不符，也可能是那頁沒分享。
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_TZ = ZoneInfo(get_settings().app_tz)

_SEARCH_URL = "https://api.notion.com/v1/search"
_PAGE_URL = "https://api.notion.com/v1/pages/{page_id}"
_BLOCKS_URL = "https://api.notion.com/v1/blocks/{block_id}/children"
# Notion API 要求帶版本標頭；此為官方穩定版本字串。
_NOTION_VERSION = "2022-06-28"
_TIMEOUT = 10.0
# 一次回幾筆——夠回答「有沒有記過 X」，又不塞爆模型上下文。
_PAGE_SIZE = 8
# 讀頁面時的上限：block 總數與巢狀深度都設限，避免把超大頁面整包塞爆模型上下文。
_MAX_BLOCKS = 300
_MAX_DEPTH = 3
# Notion 單次最多回 100 筆 block children。
_CHILDREN_PAGE_SIZE = 100
# 從連結／輸入中抓十六進位連續段（去掉 dash 後比對）；頁面 ID 是尾端的 32 碼。
# 用 {32,} 而非 {32}：標題段落若以 hex 字元（如 "Page" 的 e）緊鄰 ID，會多黏幾碼，取末 32 才對。
_HEX_RUN = re.compile(r"[0-9a-fA-F]{32,}")
# 這些 block 本身可能有 children，但不往下鑽——避免把整棵子頁面樹一起抓下來。
_NO_DESCEND = frozenset({"child_page", "child_database"})

# 攤平 block 樹的每層縮排單位。
_INDENT = "  "

# 兩支工具（search／read）共用、字字相同的回覆——集中一處，改字或多語系時不會漏改也不會改到不一致。
_MSG_AUTH_FAILED = "Notion 認證失敗（token 無效或已撤銷），請檢查 NOTION_API_KEY。"
_MSG_UNREACHABLE = "Notion 服務暫時無法連線，請稍後再試。"
_MSG_READ_FAILED = "Notion 讀取失敗，請稍後再試。"


def _headers() -> dict[str, str]:
    """組 Notion API 的請求標頭（Bearer token + 版本 + JSON）。兩支工具共用。"""
    return {
        "Authorization": f"Bearer {get_settings().notion_api_key}",
        "Notion-Version": _NOTION_VERSION,
        "Content-Type": "application/json",
    }


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

    if not get_settings().notion_enabled:
        return "尚未設定 Notion 整合（NOTION_API_KEY），無法查詢 Notion。"

    payload = {
        "query": query,
        "page_size": _PAGE_SIZE,
        # 最近編輯的優先——問「有沒有記過 X」時，新的通常更相關。
        "sort": {"direction": "descending", "timestamp": "last_edited_time"},
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as http:
            response = await http.post(_SEARCH_URL, headers=_headers(), json=payload)
    except Exception:
        logger.exception("Notion 搜尋請求例外 query=%s", query)
        return _MSG_UNREACHABLE

    if response.status_code == 401:
        # token 失效／被撤銷——設定問題，明講讓使用者去修，別誤導成「查無資料」。
        logger.warning("Notion 搜尋 401：token 無效或已撤銷")
        return _MSG_AUTH_FAILED
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


def _parse_page_id(ref: str) -> str | None:
    """從 Notion 連結或裸 ID 解析出正規化（帶 dash）的頁面 ID；解析不出回 None。

    連結尾端的 32 碼十六進位就是 ID（標題段落用 dash 相連，ID 本身無 dash）；
    使用者也可能直接貼帶 dash 的 UUID。策略：先去掉 query/fragment（避免 ?v= 的 view id 混入），
    去掉所有 dash 後找長度 ≥32 的 hex 連續段，取最後一段的末 32 碼（ID 一定在最尾，
    標題裡緊鄰的十六進位字會被多黏進來，取末 32 才對），再組回 8-4-4-4-12 的 UUID 格式。
    """
    if not ref:
        return None
    head = ref.split("?", 1)[0].split("#", 1)[0]
    runs = _HEX_RUN.findall(head.replace("-", ""))
    if not runs:
        return None
    raw = runs[-1][-32:].lower()
    return f"{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}"


def _rich_text(parts: list[dict] | None) -> str:
    """把 Notion rich_text 陣列串成純文字。"""
    return "".join(part.get("plain_text", "") for part in (parts or []))


def _format_block(block: dict, number: int) -> str | None:
    """把單一 block 轉成一行純文字（不含子 block）；空段落與不支援的型別回 None 表略過。

    number 只給 numbered_list_item 用：同層第幾個編號項（由呼叫端維護，跨層會重置）。
    圖片／檔案等非文字型別略過（表格會把每列轉成 | 分隔）——目的是給模型「讀得懂的內文」，不是完整還原版面。
    """
    block_type = block.get("type")
    data = block.get(block_type) or {}
    text = _rich_text(data.get("rich_text"))

    if block_type == "paragraph":
        return text or None  # 空段落是排版間隔，略過以免整頁都是空行
    if block_type == "heading_1":
        return f"# {text}"
    if block_type == "heading_2":
        return f"## {text}"
    if block_type == "heading_3":
        return f"### {text}"
    if block_type == "bulleted_list_item":
        return f"- {text}"
    if block_type == "numbered_list_item":
        return f"{number}. {text}"
    if block_type == "to_do":
        return f"[{'x' if data.get('checked') else ' '}] {text}"
    if block_type == "toggle":
        return f"▸ {text}"
    if block_type == "quote":
        return f"> {text}"
    if block_type == "callout":
        return f"📌 {text}"
    if block_type == "code":
        return f"```{data.get('language') or ''}\n{text}\n```"
    if block_type == "divider":
        return "———"
    if block_type == "table_row":
        # cells 是 list[list[rich_text]]；串成 | A | B | 一列。表格常放 SLA／規格／對照等關鍵資訊，不能丟。
        cells = data.get("cells") or []
        return "| " + " | ".join(_rich_text(cell) for cell in cells) + " |"
    if block_type == "child_page":
        return f"[子頁面] {data.get('title', '')}"
    if block_type == "child_database":
        return f"[子資料庫] {data.get('title', '')}"
    if block_type in {"bookmark", "embed"}:
        url = data.get("url")
        return f"[連結] {url}" if url else None
    return None


@dataclass
class _RenderBudget:
    """攤平 block 樹時共用的預算：已輸出的 block 數與是否已截斷。"""

    count: int = 0
    truncated: bool = False


async def _collect_children(
    http: httpx.AsyncClient, headers: dict[str, str], block_id: str
) -> tuple[list[dict], int | None]:
    """抓某 block 的所有直接子 block（處理分頁）。回 (blocks, error_status)；成功時 error_status 為 None。"""
    blocks: list[dict] = []
    cursor: str | None = None
    while True:
        params: dict[str, str | int] = {"page_size": _CHILDREN_PAGE_SIZE}
        if cursor:
            params["start_cursor"] = cursor
        response = await http.get(_BLOCKS_URL.format(block_id=block_id), headers=headers, params=params)
        if response.status_code // 100 != 2:
            return blocks, response.status_code
        body = response.json()
        blocks.extend(body.get("results") or [])
        cursor = body.get("next_cursor")
        if not (body.get("has_more") and cursor):
            return blocks, None


async def _render_blocks(
    http: httpx.AsyncClient,
    headers: dict[str, str],
    blocks: list[dict],
    depth: int,
    budget: _RenderBudget,
) -> list[str]:
    """遞迴把 block 清單攤平成縮排文字；受 _MAX_BLOCKS / _MAX_DEPTH 限制，超過就標記截斷。"""
    lines: list[str] = []
    number = 0  # 同層 numbered_list_item 的流水號；遇到非編號項就歸零
    for block in blocks:
        if budget.count >= _MAX_BLOCKS:
            budget.truncated = True
            break
        budget.count += 1
        block_type = block.get("type")
        number = number + 1 if block_type == "numbered_list_item" else 0
        text = _format_block(block, number)
        if text is not None:
            # code fence 可能多行，逐行縮排才對齊
            indent = _INDENT * depth
            lines.extend(f"{indent}{line}" for line in text.split("\n"))
        should_descend = block.get("has_children") and block_type not in _NO_DESCEND and depth + 1 < _MAX_DEPTH
        if should_descend:
            children, error = await _collect_children(http, headers, block["id"])
            if error is None:
                lines.extend(await _render_blocks(http, headers, children, depth + 1, budget))
            else:
                # 別靜默吞掉：子樹讀不到就明講一行，對齊「以真實資料為準、如實回報」的取向。
                logger.warning("Notion 讀取子 block 失敗 status=%s block=%s", error, block.get("id"))
                lines.append(_INDENT * (depth + 1) + "（部分內容讀取失敗）")
    return lines


async def read_notion_page(page_ref: str) -> str:
    """讀取單一 Notion 頁面的內容，攤平成文字給模型閱讀。

    Args:
        page_ref: 頁面連結（search_notion 回傳的 URL）或 32 碼頁面 ID。
    Returns:
        頁首（標題、最後編輯日）＋逐行內文；未設定、找不到、失敗都回一句說明而非拋例外。
    """
    if not page_ref or not page_ref.strip():
        return "請提供要讀取的 Notion 頁面連結或 ID。"
    page_id = _parse_page_id(page_ref)
    if not page_id:
        return "無法從輸入解析出 Notion 頁面 ID，請提供頁面的連結或 32 碼 ID。"

    if not get_settings().notion_enabled:
        return "尚未設定 Notion 整合（NOTION_API_KEY），無法讀取 Notion 頁面。"

    headers = _headers()
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as http:
            meta = await http.get(_PAGE_URL.format(page_id=page_id), headers=headers)
            if meta.status_code == 401:
                logger.warning("Notion 讀頁 401：token 無效或已撤銷")
                return _MSG_AUTH_FAILED
            if meta.status_code == 404:
                # 找不到／沒權限／傳的其實是資料庫——Notion 一律回 404，一併提示可能原因。
                return "找不到該 Notion 頁面（可能是連結有誤、它是資料庫，或尚未分享給整合）。"
            if meta.status_code // 100 != 2:
                logger.warning("Notion 讀頁 status=%s body=%s", meta.status_code, meta.text[:300])
                return _MSG_READ_FAILED

            meta_body = meta.json()
            title = _extract_title(meta_body)
            edited = _format_edited(meta_body.get("last_edited_time"))

            blocks, error = await _collect_children(http, headers, page_id)
            if error is not None:
                logger.warning("Notion 讀取 block status=%s page=%s", error, page_id)
                return _MSG_READ_FAILED
            budget = _RenderBudget()
            lines = await _render_blocks(http, headers, blocks, 0, budget)
    except Exception:
        logger.exception("Notion 讀頁請求例外 page=%s", page_ref)
        return _MSG_UNREACHABLE

    header = f"Notion 頁面「{title}」（最後編輯 {edited}）："
    if not lines:
        return f"{header}\n（此頁面沒有可讀取的文字內容。）"
    body = "\n".join(lines)
    if budget.truncated:
        body += f"\n…（內容較長，僅顯示前 {_MAX_BLOCKS} 個區塊）"
    return f"{header}\n{body}"
