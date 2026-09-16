"""Notion 搜尋工具測試：用假的 httpx client 驗格式化與容錯，不打真 API。

涵蓋：正常格式化（page/database 標題抽取）、未設定 token、空關鍵字、401、其他非 2xx、
網路例外、查無結果都轉訊息不外拋（對齊 weather 的錯誤契約），最後驗 run_tool 路由到唯讀工具。
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
