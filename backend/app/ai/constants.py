"""AI 工具的名稱常數。

tool 定義（tools.py）與分派（executor.py）共用同一份，避免兩處字面值各自漂移——
名稱對不上會讓工具靜默掉進「未知的工具」而不報錯，用常數綁在一起就不可能只改到一邊。
"""

TOOL_GET_SCHEDULE = "get_schedule"
TOOL_FIND_FREE_SLOTS = "find_free_slots"
TOOL_GET_TASKS = "get_tasks"
TOOL_GET_REMINDERS = "get_reminders"
TOOL_GET_WEATHER = "get_weather"
TOOL_SEARCH_NOTION = "search_notion"
TOOL_READ_NOTION_PAGE = "read_notion_page"
TOOL_CREATE_EVENT = "create_event"
TOOL_RESCHEDULE_EVENT = "reschedule_event"
TOOL_CANCEL_EVENT = "cancel_event"
TOOL_ADD_TASK = "add_task"
TOOL_COMPLETE_TASK = "complete_task"
TOOL_CREATE_REMINDER = "create_reminder"
TOOL_TOGGLE_REMINDER = "toggle_reminder"
TOOL_GET_MILESTONES = "get_milestones"
TOOL_CREATE_MILESTONE = "create_milestone"
TOOL_SET_MILESTONE = "set_milestone"
