"""Claude tool 定義（M3 唯讀）。description 寫清楚「何時呼叫」，提高觸發正確率。"""

TOOLS = [
    {
        "name": "get_schedule",
        "description": (
            "查詢使用者的行程。當使用者問到任何跟行程／會議／當天安排有關的問題時呼叫，"
            "例如「今天有什麼」「這週的安排」「下午有什麼會議」「明天忙不忙」。"
            "回傳指定範圍內的真實行程清單（含時間、地點、狀態）。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "要查詢的日期，格式 YYYY-MM-DD。省略則為今天。",
                },
                "range": {
                    "type": "string",
                    "enum": ["day", "week"],
                    "description": "day=只看該日；week=看該日所在的整週。省略為 day。",
                },
            },
        },
    },
    {
        "name": "find_free_slots",
        "description": (
            "找出某一天的空檔時段。當使用者問「今天有哪些空檔」「下午有空嗎」"
            "「什麼時候有時間」「排得進去嗎」時呼叫。回傳工作時間（09:00–18:00）內"
            "長度達門檻的空檔。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "要查詢的日期，格式 YYYY-MM-DD。省略則為今天。",
                },
                "min_minutes": {
                    "type": "integer",
                    "description": "最短空檔長度（分鐘），預設 30。",
                },
            },
        },
    },
]
