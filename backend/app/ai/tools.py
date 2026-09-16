"""Claude tool 定義。description 寫清楚「何時呼叫」，提高觸發正確率。

唯讀：get_schedule / find_free_slots / get_tasks / get_reminders / get_milestones。
要完成待辦或開關提醒前，先用 get_tasks / get_reminders 看清單（同 get_schedule 之於行程）。
寫入：create_event / reschedule_event / cancel_event / add_task / complete_task /
      create_reminder / toggle_reminder / create_milestone / set_milestone。
里程碑就是被標記的行程：create_milestone 等同建立一個 is_milestone 的行程，
set_milestone 只改標記、不動行程本身（真要刪行程請用 cancel_event）。
改期/取消行程要先用 get_schedule 拿到 [id=...] 再帶 event_id。
時間一律用 ISO 格式（如 2026-06-07T15:00）；system 已注入「現在時間」可據以換算。
"""

from app.ai.constants import ToolName

TOOLS = [
    {
        "name": ToolName.GET_SCHEDULE,
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
        "name": ToolName.FIND_FREE_SLOTS,
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
    {
        "name": ToolName.GET_TASKS,
        "description": (
            "查詢待辦清單。當使用者問待辦事項、說做完了某件事、或要標記完成某項待辦時呼叫——"
            "先看清單確認確實有對應項目，再決定是否 complete_task。"
            "回傳所有待辦（含完成狀態、優先級、到期）。"
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": ToolName.GET_REMINDERS,
        "description": (
            "查詢提醒清單。當使用者要開關某個提醒、或問有哪些提醒時呼叫——"
            "先看清單確認有對應項目，再 toggle_reminder。回傳所有提醒（含啟用狀態、類型）。"
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": ToolName.GET_WEATHER,
        "description": (
            "查詢某地點的天氣預報。當使用者問到天氣、或要規劃出遊／外出而需要看天氣時呼叫，"
            "例如「台中週六天氣如何」「這週末適合出去玩嗎」「明天要不要帶傘」。"
            "回傳該地點逐日預報（天氣狀況、高低溫、降雨機率）。可查未來約 16 天、過去約 3 個月內。"
            "規劃行程時可據此建議改室內／改日期。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "地點名稱，如「台中」「東京」「墾丁」。",
                },
                "date": {
                    "type": "string",
                    "description": "要查的日期，格式 YYYY-MM-DD。省略則回近期幾天的概覽。",
                },
            },
            "required": ["location"],
        },
    },
    {
        "name": ToolName.SEARCH_NOTION,
        "description": (
            "在使用者的 Notion 中以關鍵字搜尋頁面／資料庫。當使用者問到「我在 Notion 有沒有記過…」"
            "「幫我找 Notion 裡關於 X 的筆記／文件」「Notion 上的技術債清單」這類需要查 Notion 內容時呼叫。"
            "回傳符合的頁面清單（類型、標題、最後編輯日、連結）。只搜得到已分享給整合的頁面。"
            "這只回清單、不含內文；要看某頁實際寫了什麼，接著用 read_notion_page 帶該頁連結讀取。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜尋關鍵字，例如「技術債」「東京出差」「產品規劃」。",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": ToolName.READ_NOTION_PAGE,
        "description": (
            "讀取單一 Notion 頁面的實際內容。當使用者要看某頁「裡面寫了什麼」、要摘要／回答某份筆記或"
            "文件的細節時呼叫——通常先用 search_notion 找到頁面拿到連結，再用本工具讀內文。"
            "回傳頁面標題與攤平後的文字內容（含標題、清單、待辦、程式碼區塊等，巢狀會縮排）。"
            "只讀得到已分享給整合的頁面；內容過長會截斷並註明。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "page": {
                    "type": "string",
                    "description": "頁面的 Notion 連結（可直接用 search_notion 回傳的連結）或 32 碼頁面 ID。",
                },
            },
            "required": ["page"],
        },
    },
    {
        "name": ToolName.CREATE_EVENT,
        "description": (
            "新增一個行程／會議。當使用者要求安排、預約、加入新的行程時呼叫，"
            "例如「幫我約明天下午三點和 Kevin 開會一小時」「週五晚上七點訂位」。"
            "偵測到時間衝突時會回報而不建立；使用者確認仍要安排，再帶 allow_conflict=true 重呼叫。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "行程標題。"},
                "start_at": {
                    "type": "string",
                    "description": "開始時間，ISO 格式如 2026-06-07T15:00。",
                },
                "duration_min": {
                    "type": "integer",
                    "description": "持續時間（分鐘），需為正整數。",
                },
                "category": {
                    "type": "string",
                    "enum": ["meeting", "focus", "meal", "personal"],
                    "description": "分類：會議/專注/用餐/個人。省略預設 meeting。",
                },
                "location": {"type": "string", "description": "地點（可選）。"},
                "attendees": {"type": "integer", "description": "參與人數（可選）。"},
                "allow_conflict": {
                    "type": "boolean",
                    "description": "是否允許與既有行程時間衝突。預設 false（衝突就回報不建立）。",
                },
            },
            "required": ["title", "start_at", "duration_min"],
        },
    },
    {
        "name": ToolName.RESCHEDULE_EVENT,
        "description": (
            "改期一個既有行程（延後、提前、改到別的時間）。先用 get_schedule 取得目標行程的 id，"
            "再帶 event_id。例如「把下午的簡報延後一小時」→ delta_min=60；"
            "「改到明天上午十點」→ new_start_at。delta_min 與 new_start_at 擇一；"
            "若同時提供，以 new_start_at 為準（delta_min 會被忽略）。"
            "衝突時回報不執行，確認後帶 allow_conflict=true。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {
                    "type": "string",
                    "description": "目標行程 id（來自 get_schedule 的 [id=...]）。",
                },
                "new_start_at": {
                    "type": "string",
                    "description": "新開始時間，ISO 格式（絕對時間）。",
                },
                "delta_min": {
                    "type": "integer",
                    "description": "相對位移分鐘，正數延後、負數提前。",
                },
                "allow_conflict": {
                    "type": "boolean",
                    "description": "是否允許衝突。預設 false。",
                },
            },
            "required": ["event_id"],
        },
    },
    {
        "name": ToolName.CANCEL_EVENT,
        "description": (
            "取消／刪除一個行程。先用 get_schedule 取得 id 再帶 event_id。例如「取消明天的午餐」「把那個會議刪掉」。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "目標行程 id（來自 get_schedule）。"},
            },
            "required": ["event_id"],
        },
    },
    {
        "name": ToolName.ADD_TASK,
        "description": (
            "新增一項待辦事項。當使用者說「提醒我做 X」「加個待辦」「記得要…」時呼叫，"
            "例如「提醒我回覆投資人信件，今天下午五點前」。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "待辦標題。"},
                "due_at": {"type": "string", "description": "到期時間，ISO 格式（可選）。"},
                "priority": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": "優先級（可選）。",
                },
            },
            "required": ["title"],
        },
    },
    {
        "name": ToolName.COMPLETE_TASK,
        "description": (
            "把一項待辦標記為完成。當使用者說「我做完 X 了」「X 已經處理好」時呼叫。"
            "用 query 以標題關鍵字比對；若有多筆符合會回報請使用者確認。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "待辦標題的關鍵字（部分比對即可）。"},
            },
            "required": ["query"],
        },
    },
    {
        "name": ToolName.CREATE_REMINDER,
        "description": (
            "新增一則提醒。當使用者要求設定提醒、通知時呼叫，"
            "例如「每天早上八點提醒我吃維他命」「帳單到期前提醒我」。"
            "週期性提醒（每天／每週…）用 recurrence 描述，trigger_at 給代表性的觸發時間。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "提醒標題。"},
                "subtitle": {"type": "string", "description": "副標題／說明（可選）。"},
                "trigger_at": {"type": "string", "description": "觸發時間，ISO 格式（可選）。"},
                "kind": {
                    "type": "string",
                    "enum": ["meeting", "birthday", "bill", "health"],
                    "description": "類型：會議/生日/帳單/健康。省略預設 meeting。",
                },
                "recurrence": {
                    "type": "string",
                    "description": "重複規則的文字描述，如「每天」「每週一」「每月 1 號」。一次性提醒省略。",
                },
            },
            "required": ["title"],
        },
    },
    {
        "name": ToolName.TOGGLE_REMINDER,
        "description": (
            "開啟或關閉一則提醒。當使用者說「關掉 X 提醒」「把 X 提醒打開」時呼叫。"
            "用 query 以標題關鍵字比對；多筆符合會回報請確認。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "提醒標題的關鍵字（部分比對即可）。"},
                "is_enabled": {"type": "boolean", "description": "true=開啟，false=關閉。"},
            },
            "required": ["query", "is_enabled"],
        },
    },
    {
        "name": ToolName.GET_MILESTONES,
        "description": (
            "查詢使用者標記的人生里程碑（重大目標／事件）與各自的倒數天數。"
            "當使用者問「距離我的目標還有幾天」「我有哪些里程碑」「離考照還有多久」時呼叫。"
            "里程碑是被特別標記的行程，日常會議不會出現在這裡。"
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": ToolName.CREATE_MILESTONE,
        "description": (
            "新增一個人生里程碑（重大目標或事件），例如「幫我記一個目標：明年五月考完證照」"
            "「記一下 2027 年 2 月要去冰島」。里程碑會同時成為行事曆上的行程，並出現在人生倒數頁。"
            "只給日期沒給時間時，預設排在當天上午 9 點、長度一小時。"
            "一般的會議／看診／吃飯請改用 create_event，別標成里程碑。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "里程碑名稱，例如「考完 PMP 證照」。"},
                "target_date": {
                    "type": "string",
                    "description": "目標日期，格式 YYYY-MM-DD。",
                },
                "start_time": {
                    "type": "string",
                    "description": "當天的時間，格式 HH:MM（可選，省略為 09:00）。",
                },
                "note": {"type": "string", "description": "備註（可選），例如達成條件。"},
            },
            "required": ["title", "target_date"],
        },
    },
    {
        "name": ToolName.SET_MILESTONE,
        "description": (
            "把既有行程標成里程碑，或取消其里程碑標記。"
            "例如「把下個月的產品發表會設成里程碑」→ is_milestone=true；"
            "「取消婚禮的里程碑標記」→ is_milestone=false（行程本身會保留，只是不再倒數）。"
            "用 query 以標題關鍵字比對；多筆符合會回報請確認。"
            "若使用者是要「刪掉這個行程」而非取消標記，請改用 cancel_event。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "行程標題的關鍵字（部分比對即可）。"},
                "is_milestone": {
                    "type": "boolean",
                    "description": "true=標成里程碑，false=取消標記。",
                },
            },
            "required": ["query", "is_milestone"],
        },
    },
]
