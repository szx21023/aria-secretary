"""AI 工具的名稱列舉。

tool 定義（tools.py）與分派（executor.py）共用同一份，避免兩處字面值各自漂移——
名稱對不上會讓工具靜默掉進「未知的工具」而不報錯，綁在同一個列舉就不可能只改到一邊。

沿用專案慣例的 `class X(str, Enum)`（見 CLAUDE.md）：成員即字串，`==`、集合成員判斷、
JSON 序列化都以字串值運作，與純字串常數行為等價，另外還能 iterate／驗證名稱。
"""

from enum import Enum, unique


@unique
class ToolName(str, Enum):
    GET_SCHEDULE = "get_schedule"
    FIND_FREE_SLOTS = "find_free_slots"
    GET_TASKS = "get_tasks"
    GET_REMINDERS = "get_reminders"
    GET_WEATHER = "get_weather"
    SEARCH_NOTION = "search_notion"
    READ_NOTION_PAGE = "read_notion_page"
    CREATE_EVENT = "create_event"
    RESCHEDULE_EVENT = "reschedule_event"
    CANCEL_EVENT = "cancel_event"
    ADD_TASK = "add_task"
    COMPLETE_TASK = "complete_task"
    CREATE_REMINDER = "create_reminder"
    TOGGLE_REMINDER = "toggle_reminder"
    GET_MILESTONES = "get_milestones"
    CREATE_MILESTONE = "create_milestone"
    SET_MILESTONE = "set_milestone"
