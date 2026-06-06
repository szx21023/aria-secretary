from typing import Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import MessageRole


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


class DoneEvent(TypedDict):
    type: Literal["done"]
    text: str  # 完整回覆（供持久化）


class ErrorEvent(TypedDict):
    type: Literal["error"]
    message: str


ChatEvent = DeltaEvent | ToolEvent | DoneEvent | ErrorEvent
