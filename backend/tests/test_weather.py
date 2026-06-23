"""天氣工具測試：用假的 httpx client 驗 geocode + forecast 兩段式，

以及容錯（查無地點／網路例外／壞日期都轉訊息不外拋），最後驗 run_tool 路由到唯讀工具。
不打真 API——以 url 子字串分流 geocode 與 forecast 的假回應。
"""

import pytest

from app.ai import executor, weather

pytestmark = pytest.mark.asyncio


class _FakeResp:
    def __init__(self, payload, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload


class _FakeHTTP:
    """以 url 子字串挑回應：{'nominatim': resp, 'forecast': resp}；值是 _FakeResp 或要拋的例外。

    記錄每次 get 的 params 與 headers，讓測試能驗請求內容（如 Nominatim 必帶的 User-Agent）。
    """

    last_params: list[dict] = []
    last_headers: list[dict | None] = []

    def __init__(self, routes: dict):
        self._routes = routes

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params, headers=None):
        _FakeHTTP.last_params.append(params)
        _FakeHTTP.last_headers.append(headers)
        for key, val in self._routes.items():
            if key in url:
                if isinstance(val, Exception):
                    raise val
                return val
        raise AssertionError(f"未預期的 url：{url}")


def _patch(monkeypatch, routes: dict) -> None:
    _FakeHTTP.last_params = []
    _FakeHTTP.last_headers = []
    monkeypatch.setattr(weather.httpx, "AsyncClient", lambda timeout: _FakeHTTP(routes))


# Nominatim geocoding 回傳的是陣列，每筆含 lat/lon（字串）與 display_name。
_GEO_OK = _FakeResp([{"lat": "24.14", "lon": "120.68", "display_name": "臺中市, 臺灣"}])


async def test_get_weather_single_date_formats_forecast(monkeypatch):
    forecast = _FakeResp(
        {
            "daily": {
                "time": ["2026-06-27"],
                "weather_code": [63],
                "temperature_2m_max": [28.4],
                "temperature_2m_min": [24.1],
                "precipitation_probability_max": [70],
            }
        }
    )
    _patch(monkeypatch, {"nominatim": _GEO_OK, "forecast": forecast})
    out = await weather.get_weather("台中", "2026-06-27")
    assert "臺中市" in out
    assert "2026-06-27" in out
    assert "中雨" in out  # WMO 63
    assert "24–28°C" in out
    assert "降雨機率 70%" in out
    # 帶了 date 就該以 start/end 鎖單日，而非用 forecast_days
    fparams = _FakeHTTP.last_params[-1]
    assert fparams["start_date"] == "2026-06-27"
    assert fparams["end_date"] == "2026-06-27"


async def test_get_weather_no_date_uses_multi_day_outlook(monkeypatch):
    forecast = _FakeResp(
        {
            "daily": {
                "time": ["2026-06-23", "2026-06-24", "2026-06-25"],
                "weather_code": [0, 2, 80],
                "temperature_2m_max": [33, 32, 30],
                "temperature_2m_min": [26, 26, 25],
                "precipitation_probability_max": [10, 20, 60],
            }
        }
    )
    _patch(monkeypatch, {"nominatim": _GEO_OK, "forecast": forecast})
    out = await weather.get_weather("台中")
    # 三天各自成行（以日期斷言，比數換行的魔術數字更有意義）
    for day in ("2026-06-23", "2026-06-24", "2026-06-25"):
        assert day in out
    assert "晴朗" in out
    assert _FakeHTTP.last_params[-1].get("forecast_days") == weather._DEFAULT_DAYS
    assert "start_date" not in _FakeHTTP.last_params[-1]
    # geocode（第一次呼叫）必帶 Nominatim 要求的 User-Agent，否則正式環境會被 403
    assert "User-Agent" in (_FakeHTTP.last_headers[0] or {})


async def test_get_weather_location_not_found(monkeypatch):
    _patch(monkeypatch, {"nominatim": _FakeResp([])})  # Nominatim 查無回空陣列
    out = await weather.get_weather("不存在的地方xyz")
    assert "查不到" in out


async def test_get_weather_network_error_on_geocode_returns_message(monkeypatch):
    _patch(monkeypatch, {"nominatim": RuntimeError("connection reset")})
    out = await weather.get_weather("台中")
    assert "查不到" in out or "無法連線" in out


async def test_get_weather_forecast_out_of_range_4xx(monkeypatch):
    # Open-Meteo 對超範圍日期實際回 400 + {error, reason}——要講「超出範圍」，不可誤報連線錯。
    # （這是真打 API 才發現的真實訊號：不是 200+空 daily，而是 4xx。）
    rejected = _FakeResp({"error": True, "reason": "out of allowed range"}, status_code=400)
    _patch(monkeypatch, {"nominatim": _GEO_OK, "forecast": rejected})
    out = await weather.get_weather("台中", "2099-01-01")
    assert "超出可查範圍" in out
    assert "無法連線" not in out


async def test_get_weather_forecast_empty_days_2xx_also_no_forecast(monkeypatch):
    # 防禦：2xx 但 daily 無資料也歸到「沒有可用預報」這條
    _patch(monkeypatch, {"nominatim": _GEO_OK, "forecast": _FakeResp({"daily": {"time": []}})})
    out = await weather.get_weather("台中", "2099-01-01")
    assert "沒有可用預報" in out


async def test_get_weather_forecast_transport_failure_distinct_message(monkeypatch):
    # forecast 連線例外 → status None → 該講「無法連線」，不可誤報成「超出範圍」誤導使用者改日期
    _patch(monkeypatch, {"nominatim": _GEO_OK, "forecast": RuntimeError("timeout")})
    out = await weather.get_weather("台中", "2026-06-27")
    assert "無法連線" in out
    assert "超出" not in out


async def test_get_weather_forecast_5xx_returns_connection_message(monkeypatch):
    # 上游 5xx 是真失敗 → 連線錯訊息（與 4xx 超範圍明確區分）
    _patch(monkeypatch, {"nominatim": _GEO_OK, "forecast": _FakeResp({}, status_code=503)})
    out = await weather.get_weather("台中", "2026-06-27")
    assert "無法連線" in out


async def test_get_weather_non_2xx_geocode_returns_message(monkeypatch):
    # geocode 非 2xx → _geocode 回 None → 查不到訊息（與「空陣列查無」「例外」殊途同歸）
    _patch(monkeypatch, {"nominatim": _FakeResp([], status_code=500)})
    out = await weather.get_weather("台中")
    assert "查不到" in out or "無法連線" in out


async def test_get_weather_geocode_result_missing_coords_treated_as_not_found(monkeypatch):
    # Nominatim 回了結構但缺 lat/lon：必須當查無，不能讓 geo["lat"] 丟 KeyError 炸出去
    _patch(monkeypatch, {"nominatim": _FakeResp([{"display_name": "某處"}])})
    out = await weather.get_weather("怪地點")
    assert "查不到" in out


async def test_get_weather_handles_none_fields_in_daily(monkeypatch):
    # Open-Meteo 可能在某天回 null 溫度／降雨機率，且陣列長度仍對齊——不可丟 TypeError
    forecast = _FakeResp(
        {
            "daily": {
                "time": ["2026-06-27"],
                "weather_code": [3],
                "temperature_2m_max": [None],
                "temperature_2m_min": [None],
                "precipitation_probability_max": [None],
            }
        }
    )
    _patch(monkeypatch, {"nominatim": _GEO_OK, "forecast": forecast})
    out = await weather.get_weather("台中", "2026-06-27")
    assert "2026-06-27" in out
    assert "溫度不明" in out
    assert "降雨機率" not in out  # None 時整段省略


async def test_get_weather_handles_short_value_arrays(monkeypatch):
    # time 比值陣列長（缺欄位）時逐 index 守衛要擋住 IndexError，缺的退回「不明」
    forecast = _FakeResp(
        {
            "daily": {
                "time": ["2026-06-23", "2026-06-24", "2026-06-25"],
                "weather_code": [0],
                "temperature_2m_max": [30],
                "temperature_2m_min": [24],
                "precipitation_probability_max": [10],
            }
        }
    )
    _patch(monkeypatch, {"nominatim": _GEO_OK, "forecast": forecast})
    out = await weather.get_weather("台中")
    for day in ("2026-06-23", "2026-06-24", "2026-06-25"):
        assert day in out
    assert "天氣不明" in out  # 第 2、3 天沒有對應 weather_code
    assert "溫度不明" in out


async def test_describe_code_unknown_and_none():
    assert weather._describe_code(63) == "中雨"  # 已知碼
    assert weather._describe_code(100) == "天氣狀況代碼 100"  # 未列出的退回代碼
    assert weather._describe_code(None) == "天氣不明"


async def test_place_label_branches():
    # 長 display_name → 取首段＋末段（國名）
    assert weather._place_label({"display_name": "信義區, 台北市, 北部, 臺灣"}, "x") == "信義區, 臺灣"
    # 兩段以內直接保留
    assert weather._place_label({"display_name": "臺北市, 臺灣"}, "x") == "臺北市, 臺灣"
    # 無 display_name 退回 name
    assert weather._place_label({"name": "墾丁"}, "x") == "墾丁"
    # 兩者皆無 → 退回原始查詢字串
    assert weather._place_label({}, "原始地名") == "原始地名"


async def test_get_weather_bad_date_no_http_call(monkeypatch):
    _patch(monkeypatch, {})  # 任何 http 呼叫都會 AssertionError
    out = await weather.get_weather("台中", "2026/06/27")
    assert "無法解析" in out
    assert _FakeHTTP.last_params == []


async def test_get_weather_empty_location(monkeypatch):
    _patch(monkeypatch, {})
    out = await weather.get_weather("   ")
    assert "請提供" in out
    assert _FakeHTTP.last_params == []


async def test_run_tool_routes_get_weather_readonly(db, monkeypatch):
    async def _stub(location, date=None):
        return f"weather:{location}:{date}"

    monkeypatch.setattr(executor, "get_weather", _stub)
    out = await executor.run_tool(db, "get_weather", {"location": "台中", "date": "2026-06-27"})
    assert out.text == "weather:台中:2026-06-27"
    assert out.changed is None  # 唯讀工具不標改動
