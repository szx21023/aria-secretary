"""天氣查詢：地名→經緯度→逐日預報，整理成文字給模型閱讀。

兩段式且刻意分家：
- geocoding 用 OSM Nominatim。實測 Open-Meteo 自帶的 geocoding 對台灣中文地名幾乎全查不到
  （台中／台北／墾丁皆 NONE），甚至「高雄」會誤配到四川的同名地；Nominatim 對中文地名正確。
- forecast 用 Open-Meteo（免費、免 key），只需經緯度。
兩者都用 httpx 直打，不引額外 SDK——同 line/client 的取向。

回傳「給模型讀的文字」而非結構：查不到地點、超出範圍、網路例外都轉成一句話回報，
讓 agent 能照實告訴使用者，而不是把例外往 chat loop 外炸。日期範圍受 Open-Meteo 限制
（約未來 16 天、過去約 3 個月），超出會被拒，照樣轉成訊息。
"""

import logging
from datetime import date
from zoneinfo import ZoneInfo

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_TZ = ZoneInfo(get_settings().app_tz)

_GEOCODE_URL = "https://nominatim.openstreetmap.org/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_TIMEOUT = 10.0

# Nominatim 使用條款要求帶可識別的 User-Agent，並限 1 req/s（個人助理偶發查詢遠低於此）。
_GEO_HEADERS = {"User-Agent": "aria-secretary/1.0 (personal scheduling assistant)"}

# 省略 date 時給幾天的概覽（夠涵蓋「這週末」；模型問特定日會自己帶 date）。
_DEFAULT_DAYS = 3

# WMO weather code → 中文描述。涵蓋常見碼，未列出的退回「天氣狀況代碼 N」。
_WMO: dict[int, str] = {
    0: "晴朗",
    1: "大致晴朗",
    2: "部分多雲",
    3: "陰天",
    45: "有霧",
    48: "霧凇",
    51: "毛毛雨",
    53: "小雨",
    55: "中雨",
    56: "凍毛雨",
    57: "強凍毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "凍雨",
    67: "強凍雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "霰",
    80: "局部陣雨",
    81: "陣雨",
    82: "強陣雨",
    85: "陣雪",
    86: "強陣雪",
    95: "雷雨",
    96: "雷雨夾冰雹",
    99: "強雷雨夾冰雹",
}


def _describe_code(code: int | None) -> str:
    if code is None:
        return "天氣不明"
    return _WMO.get(code, f"天氣狀況代碼 {code}")


async def _get(url: str, params: dict, headers: dict | None = None):
    """GET 一個回 JSON 的 endpoint，回 (status_code, payload)。

    刻意保留 status：呼叫端要靠它區分「連不上／5xx（真失敗，請稍後再試）」與
    「4xx 被拒（如 Open-Meteo 對超範圍日期回的 error body，改參數才有用）」。
    連線例外回 (None, None)；body 非 JSON 回 (status, None)。非 2xx 一律記 log。
    """
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as http:
            resp = await http.get(url, params=params, headers=headers)
    except Exception:
        logger.exception("天氣 API 請求例外 url=%s", url)
        return None, None
    if resp.status_code // 100 != 2:
        logger.warning("天氣 API %s status=%s body=%s", url, resp.status_code, resp.text)
    try:
        return resp.status_code, resp.json()
    except Exception:
        return resp.status_code, None


async def _geocode(location: str) -> dict | None:
    """地名→第一筆地理位置（Nominatim，含 lat/lon 與 display_name）；查無或失敗回 None。"""
    status, data = await _get(
        _GEOCODE_URL,
        {"q": location, "format": "json", "limit": 1, "accept-language": "zh-TW"},
        headers=_GEO_HEADERS,
    )
    if status is None or status // 100 != 2 or not data:  # 失敗、非 2xx、或查無（空陣列）
        return None
    first = data[0]
    # Nominatim 正常命中一定帶 lat/lon；缺了代表回了非預期結構，當查無處理，
    # 別讓後面 geo["lat"] 丟 KeyError 炸出 chat loop（破壞本模組「錯誤轉訊息」契約）。
    if not isinstance(first, dict) or first.get("lat") is None or first.get("lon") is None:
        logger.warning("Nominatim 回應缺 lat/lon location=%s payload=%s", location, first)
        return None
    return first


def _place_label(geo: dict, fallback: str) -> str:
    """從 Nominatim 的 display_name 組出簡潔地名，如「台中, 臺灣」；取首段＋國名。"""
    disp = geo.get("display_name") or geo.get("name") or fallback
    parts = [p.strip() for p in disp.split(",") if p.strip()]
    if not parts:
        return fallback
    if len(parts) <= 2:
        return ", ".join(parts)
    return f"{parts[0]}, {parts[-1]}"  # 首段（地點）＋末段（國家）


async def get_weather(location: str, date_str: str | None = None) -> str:
    """查 location 的天氣預報。date_str 給某日（YYYY-MM-DD）則只回那天，
    省略則回今天起 _DEFAULT_DAYS 天的概覽。回傳給模型閱讀的文字。"""
    if not location or not location.strip():
        return "請提供要查天氣的地點。"

    target: date | None = None
    if date_str:
        try:
            target = date.fromisoformat(date_str)
        except ValueError:
            return f"日期格式無法解析：{date_str!r}，請用 YYYY-MM-DD，或省略代表近期。"

    geo = await _geocode(location)
    if geo is None:
        return f"查不到「{location}」這個地點，或天氣服務暫時無法連線，請稍後再試或換個說法。"

    params: dict = {
        "latitude": geo["lat"],
        "longitude": geo["lon"],
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "auto",  # 回傳以該地點當地時間為準
    }
    if target is not None:
        params["start_date"] = target.isoformat()
        params["end_date"] = target.isoformat()
    else:
        params["forecast_days"] = _DEFAULT_DAYS

    status, data = await _get(_FORECAST_URL, params)
    if status is None or status // 100 == 5:
        # 連不上或上游 5xx——真的失敗，別跟「超出範圍」混為一談誤導使用者去改日期。
        return f"天氣服務暫時無法連線，拿不到「{location}」的天氣，請稍後再試。"
    daily = (data or {}).get("daily") or {}
    days: list[str] = daily.get("time") or []
    if not days:
        # 走到這通常是 Open-Meteo 對超範圍日期／壞參數回 4xx（帶 error/reason），或 2xx 但無資料。
        if target is not None:
            return (
                f"「{location}」{target.isoformat()} 沒有可用預報"
                "——該日期可能超出可查範圍（約未來 16 天、過去約 3 個月內）。"
            )
        return f"拿不到「{location}」的近期預報，請稍後再試。"

    codes = daily.get("weather_code") or []
    tmax = daily.get("temperature_2m_max") or []
    tmin = daily.get("temperature_2m_min") or []
    pop = daily.get("precipitation_probability_max") or []
    label = _place_label(geo, location)

    lines = [f"{label} 天氣預報："]
    for i, day in enumerate(days):
        code = codes[i] if i < len(codes) else None
        hi = tmax[i] if i < len(tmax) else None
        lo = tmin[i] if i < len(tmin) else None
        rain = pop[i] if i < len(pop) else None
        temp = f"{round(lo)}–{round(hi)}°C" if hi is not None and lo is not None else "溫度不明"
        rain_txt = f"，降雨機率 {round(rain)}%" if rain is not None else ""
        lines.append(f"- {day}：{_describe_code(code)}，{temp}{rain_txt}")
    return "\n".join(lines)
