from enum import Enum
from typing import Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import MessageRole

# 可被寫入工具改動的資源；同時是 SSE state_changed 的 resource 值與前端 TanStack query key。
# 收斂成 Literal 後，executor 端寫錯（如 "event"）會在 type-check 就擋下，不會默默不刷新。
ChangedResource = Literal["events", "tasks", "reminders"]


class EventType(str, Enum):
    """SSE 事件 type 值的單一來源：agent 產生端 yield、chat/cli 消費端比對都引用它，不再散字面字串。

    str 混入讓 json.dumps 直接序列化成字串（wire 不變），且 EventType.delta == "delta" 為 True，
    既有以純字串做 dict 比對的測試照樣通過。
    """

    delta = "delta"
    tool = "tool"
    state_changed = "state_changed"
    done = "done"
    error = "error"


# 使用者單則訊息長度上限（字元）
MESSAGE_MAX_LENGTH = 4000


class ChatRequestSchema(BaseModel):
    message: str = Field(min_length=1, max_length=MESSAGE_MAX_LENGTH)


class MessageReadSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role: MessageRole
    content: str


# ---- SSE 事件協定（agent 產生 → chat 透傳 → 前端消費的唯一來源）----
class DeltaEvent(TypedDict):
    type: Literal[EventType.delta]
    text: str  # 秘書回覆的文字片段


class ToolEvent(TypedDict):
    type: Literal[EventType.tool]
    name: str  # 正在呼叫的工具名


class StateChangedEvent(TypedDict):
    type: Literal[EventType.state_changed]
    resource: ChangedResource  # 前端據此 invalidate 對應 query


class DoneEvent(TypedDict):
    type: Literal[EventType.done]
    text: str  # 完整回覆（供持久化）


class ErrorEvent(TypedDict):
    type: Literal[EventType.error]
    message: str


ChatEvent = DeltaEvent | ToolEvent | StateChangedEvent | DoneEvent | ErrorEvent
