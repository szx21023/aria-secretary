from pydantic import BaseModel, ConfigDict

from app.models.enums import MessageRole


class ChatRequest(BaseModel):
    message: str


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role: MessageRole
    content: str
