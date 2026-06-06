from typing import Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import MessageRole

# 可被寫入工具改動的資源；同時是 SSE state_changed 的 resource 值與前端 TanStack query key。
# 收斂成 Literal 後，executor 端寫錯（如 "event"）會在 type-check 就擋下，不會默默不刷新。
ChangedResource = Literal["events", "tasks", "reminders"]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role: MessageRole
    content: str


# ---- SSE 事件協定（agent 產生 → chat 透傳 → 前端消費的唯一來源）----
class DeltaEvent(TypedDict):
    type: Literal["delta"]
    text: str  # 秘書回覆的文字片段


class ToolEvent(TypedDict):
    type: Literal["tool"]
    name: str  # 正在呼叫的工具名


class StateChangedEvent(TypedDict):
    type: Literal["state_changed"]
    resource: ChangedResource  # 前端據此 invalidate 對應 query


class DoneEvent(TypedDict):
    type: Literal["done"]
    text: str  # 完整回覆（供持久化）


class ErrorEvent(TypedDict):
    type: Literal["error"]
    message: str


ChatEvent = DeltaEvent | ToolEvent | StateChangedEvent | DoneEvent | ErrorEvent
