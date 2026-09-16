"""Notion 搜尋／讀頁工具測試：用假的 httpx client 驗格式化與容錯，不打真 API。

search_notion 涵蓋：正常格式化（page/database 標題抽取）、未設定 token、空關鍵字、401、其他非 2xx、
網路例外、查無結果都轉訊息不外拋（對齊 weather 的錯誤契約）。
read_notion_page 涵蓋：block 格式化（標題/清單/待辦/程式碼）、巢狀縮排、頁面 ID 解析、未設定、
空/無法解析輸入、401/404/其他非 2xx、網路例外、空頁、超長截斷。
最後各驗一次 run_tool 路由到對應唯讀工具。
"""

from types import SimpleNamespace

import pytest

from app.ai import executor, notion

pytestmark = pytest.mark.asyncio


class _FakeResp:
    def __init__(self, payload, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload


class _FakeHTTP:
    """記錄 post 的 url/headers/json，並回預設回應或拋預設例外。"""

    last_headers: dict | None = None
    last_json: dict | None = None

    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        _FakeHTTP.last_headers = headers
        _FakeHTTP.last_json = json
        if isinstance(self._resp, Exception):
            raise self._resp
        return self._resp


def _patch(monkeypatch, resp, *, enabled: bool = True) -> None:
    _FakeHTTP.last_headers = None
    _FakeHTTP.last_json = None
    monkeypatch.setattr(notion.httpx, "AsyncClient", lambda timeout: _FakeHTTP(resp))
    monkeypatch.setattr(
        notion,
        "get_settings",
        lambda: SimpleNamespace(notion_enabled=enabled, notion_api_key="ntn_test" if enabled else ""),
    )


def _page(title: str, url: str = "https://notion.so/x", edited: str = "2026-09-14T02:30:00.000Z") -> dict:
    return {
        "object": "page",
        "url": url,
        "last_edited_time": edited,
        "properties": {"Name": {"type": "title", "title": [{"plain_text": title}]}},
    }


async def test_search_formats_page_and_database(monkeypatch):
    resp = _FakeResp(
        {
            "results": [
                _page("技術債清單"),
                {
                    "object": "database",
                    "url": "https://notion.so/db",
                    "last_edited_time": "2026-09-10T00:00:00.000Z",
                    "title": [{"plain_text": "專案任務庫"}],
                },
            ]
        }
    )
    _patch(monkeypatch, resp)
    out = await notion.search_notion("技術債")
    assert "找到 2 筆" in out
    assert "[頁面] 技術債清單" in out
    assert "[資料庫] 專案任務庫" in out
    assert "2026-09-14" in out  # last_edited 有被格式化成日期
    assert "https://notion.so/x" in out
    # 請求內容：帶 Bearer + Notion-Version，且以 last_edited_time 降冪排序
    assert _FakeHTTP.last_headers["Authorization"] == "Bearer ntn_test"
    assert _FakeHTTP.last_headers["Notion-Version"] == notion._NOTION_VERSION
    assert _FakeHTTP.last_json["sort"]["timestamp"] == "last_edited_time"


async def test_search_truncated_signals_more(monkeypatch):
    # has_more=True：只回了前幾筆，訊息必須點明「可能還有更多」，不可講成找到的就是全部
    resp = _FakeResp({"results": [_page("會議紀錄一"), _page("會議紀錄二")], "has_more": True})
    _patch(monkeypatch, resp)
    out = await notion.search_notion("會議")
    assert "可能還有更多" in out
    assert "找到 2 筆" not in out  # 別把截斷講成全部


async def test_format_edited_converts_to_local_tz():
    # UTC 20:00 = 台北隔天 04:00：轉在地時區後日期要進位到隔天，不可停在 UTC 當天
    assert notion._format_edited("2026-09-13T20:00:00.000Z") == "2026-09-14"
    # 解析不了原樣回、缺值回「時間不明」
    assert notion._format_edited("not-a-date") == "not-a-date"
    assert notion._format_edited(None) == "時間不明"


async def test_search_not_configured_no_http_call(monkeypatch):
    _patch(monkeypatch, _FakeResp({}), enabled=False)
    out = await notion.search_notion("技術債")
    assert "尚未設定" in out
    assert _FakeHTTP.last_json is None  # 未設定就不該打 API


async def test_search_empty_query_no_http_call(monkeypatch):
    _patch(monkeypatch, _FakeResp({}))
    out = await notion.search_notion("   ")
    assert "請提供" in out
    assert _FakeHTTP.last_json is None


async def test_search_401_returns_auth_message(monkeypatch):
    _patch(monkeypatch, _FakeResp({"message": "unauthorized"}, status_code=401))
    out = await notion.search_notion("技術債")
    assert "認證失敗" in out


async def test_search_other_non_2xx_returns_generic_failure(monkeypatch):
    _patch(monkeypatch, _FakeResp({}, status_code=500))
    out = await notion.search_notion("技術債")
    assert "查詢失敗" in out


async def test_search_network_error_returns_message(monkeypatch):
    _patch(monkeypatch, RuntimeError("connection reset"))
    out = await notion.search_notion("技術債")
    assert "無法連線" in out


async def test_search_no_results_hints_sharing(monkeypatch):
    _patch(monkeypatch, _FakeResp({"results": []}))
    out = await notion.search_notion("不存在的關鍵字")
    assert "找不到" in out
    assert "分享" in out  # 提示可能是沒分享給整合


async def test_extract_title_branches():
    assert notion._extract_title(_page("我的頁")) == "我的頁"
    assert notion._extract_title({"object": "database", "title": [{"plain_text": "庫"}]}) == "庫"
    # 無標題結構 → 不炸，回佔位字串
    assert notion._extract_title({"object": "page", "properties": {}}) == "（無標題）"


async def test_run_tool_routes_search_notion_readonly(db, monkeypatch):
    async def _stub(query):
        return f"notion:{query}"

    monkeypatch.setattr(executor, "search_notion", _stub)
    out = await executor.run_tool(db, "search_notion", {"query": "技術債"})
    assert out.text == "notion:技術債"
    assert out.changed is None  # 唯讀工具不標改動


# ── read_notion_page ────────────────────────────────────────────────
# 這頁的 32 碼 ID 與其正規化（帶 dash）形式；URL 尾端就是無 dash 的那 32 碼。
_RAW_ID = "1a2b3c4d5e6f7890abcdef1234567890"
_DASHED_ID = "1a2b3c4d-5e6f-7890-abcd-ef1234567890"


class _ReadHTTP:
    """讀頁面用的假 client：GET /pages/... 回 meta，GET /blocks/{id}/children 依 id 回子 block。"""

    last_headers: dict | None = None

    def __init__(self, meta=None, children: dict | None = None, error: Exception | None = None):
        self._meta = meta
        self._children = children or {}  # block_id(dashed) -> _FakeResp
        self._error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, headers=None, params=None):
        _ReadHTTP.last_headers = headers
        if self._error is not None:
            raise self._error
        if "/pages/" in url:
            return self._meta
        block_id = url.split("/blocks/")[1].split("/children")[0]
        return self._children.get(block_id, _FakeResp({"results": []}))


def _patch_read(monkeypatch, http, *, enabled: bool = True) -> None:
    _ReadHTTP.last_headers = None
    monkeypatch.setattr(notion.httpx, "AsyncClient", lambda timeout: http)
    monkeypatch.setattr(
        notion,
        "get_settings",
        lambda: SimpleNamespace(notion_enabled=enabled, notion_api_key="ntn_test" if enabled else ""),
    )


def _meta_page(title: str = "我的筆記", edited: str = "2026-09-14T02:30:00.000Z") -> _FakeResp:
    return _FakeResp(
        {
            "object": "page",
            "last_edited_time": edited,
            "properties": {"Name": {"type": "title", "title": [{"plain_text": title}]}},
        }
    )


def _blk(block_type: str, text: str = "", **extra) -> dict:
    return {"type": block_type, block_type: {"rich_text": [{"plain_text": text}], **extra}}


async def test_read_formats_common_blocks(monkeypatch):
    children = _FakeResp(
        {
            "results": [
                _blk("heading_2", "重點"),
                _blk("paragraph", "這是一段內文"),
                _blk("bulleted_list_item", "項目一"),
                _blk("to_do", "買牛奶", checked=True),
                _blk("numbered_list_item", "第一步"),
                _blk("code", "print(1)", language="python"),
            ]
        }
    )
    http = _ReadHTTP(meta=_meta_page("我的筆記"), children={_DASHED_ID: children})
    _patch_read(monkeypatch, http)
    out = await notion.read_notion_page(_DASHED_ID)
    assert "Notion 頁面「我的筆記」" in out
    assert "2026-09-14" in out  # 最後編輯日格式化
    assert "## 重點" in out
    assert "這是一段內文" in out
    assert "- 項目一" in out
    assert "[x] 買牛奶" in out  # 勾選狀態
    assert "1. 第一步" in out  # numbered 帶流水號
    assert "```python" in out and "print(1)" in out
    assert _ReadHTTP.last_headers["Authorization"] == "Bearer ntn_test"


async def test_read_nested_blocks_indented(monkeypatch):
    toggle = _blk("toggle", "展開我")
    toggle["has_children"] = True
    toggle["id"] = "child-1"
    top = _FakeResp({"results": [toggle]})
    nested = _FakeResp({"results": [_blk("paragraph", "巢狀內容")]})
    http = _ReadHTTP(meta=_meta_page(), children={_DASHED_ID: top, "child-1": nested})
    _patch_read(monkeypatch, http)
    out = await notion.read_notion_page("https://www.notion.so/Team/My-Page-1a2b3c4d5e6f7890abcdef1234567890")
    assert "▸ 展開我" in out
    assert "\n  巢狀內容" in out  # 子 block 縮排兩格


async def test_parse_page_id_from_url_dashed_raw_and_invalid():
    assert notion._parse_page_id("https://www.notion.so/Team/My-Page-" + _RAW_ID) == _DASHED_ID
    assert notion._parse_page_id(_DASHED_ID) == _DASHED_ID
    assert notion._parse_page_id(_RAW_ID) == _DASHED_ID
    assert notion._parse_page_id("https://notion.so/no-id-here") is None
    assert notion._parse_page_id("") is None


async def test_read_empty_ref_no_http_call(monkeypatch):
    _patch_read(monkeypatch, _ReadHTTP(), enabled=True)
    out = await notion.read_notion_page("   ")
    assert "請提供" in out


async def test_read_unparseable_ref():
    out = await notion.read_notion_page("just some words")
    assert "無法" in out and "解析" in out


async def test_read_not_configured(monkeypatch):
    _patch_read(monkeypatch, _ReadHTTP(), enabled=False)
    out = await notion.read_notion_page(_DASHED_ID)
    assert "尚未設定" in out


async def test_read_401_returns_auth_message(monkeypatch):
    _patch_read(monkeypatch, _ReadHTTP(meta=_FakeResp({}, status_code=401)))
    out = await notion.read_notion_page(_DASHED_ID)
    assert "認證失敗" in out


async def test_read_404_returns_not_found(monkeypatch):
    _patch_read(monkeypatch, _ReadHTTP(meta=_FakeResp({}, status_code=404)))
    out = await notion.read_notion_page(_DASHED_ID)
    assert "找不到" in out


async def test_read_other_non_2xx_returns_generic_failure(monkeypatch):
    _patch_read(monkeypatch, _ReadHTTP(meta=_FakeResp({}, status_code=500)))
    out = await notion.read_notion_page(_DASHED_ID)
    assert "讀取失敗" in out


async def test_read_network_error_returns_message(monkeypatch):
    _patch_read(monkeypatch, _ReadHTTP(error=RuntimeError("connection reset")))
    out = await notion.read_notion_page(_DASHED_ID)
    assert "無法連線" in out


async def test_read_empty_page_reports_no_content(monkeypatch):
    http = _ReadHTTP(meta=_meta_page("空頁"), children={_DASHED_ID: _FakeResp({"results": []})})
    _patch_read(monkeypatch, http)
    out = await notion.read_notion_page(_DASHED_ID)
    assert "沒有可讀取的文字內容" in out


async def test_read_truncates_oversized_page(monkeypatch):
    over = [_blk("paragraph", f"行{index}") for index in range(notion._MAX_BLOCKS + 5)]
    http = _ReadHTTP(meta=_meta_page(), children={_DASHED_ID: _FakeResp({"results": over})})
    _patch_read(monkeypatch, http)
    out = await notion.read_notion_page(_DASHED_ID)
    assert "僅顯示前" in out


async def test_run_tool_routes_read_notion_page_readonly(db, monkeypatch):
    async def _stub(page):
        return f"page:{page}"

    monkeypatch.setattr(executor, "read_notion_page", _stub)
    out = await executor.run_tool(db, "read_notion_page", {"page": "xyz"})
    assert out.text == "page:xyz"
    assert out.changed is None  # 唯讀工具不標改動
