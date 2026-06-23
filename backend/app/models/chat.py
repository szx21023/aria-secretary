from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import MessageRole


class Conversation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "conversations"

    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # 最後一個透過 LINE 跟秘書講話的人；推播找不到設定的收件人時用它當預設目標。
    line_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "messages"

    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[MessageRole] = mapped_column(SAEnum(MessageRole))
    content: Mapped[str] = mapped_column(Text, default="")
    # 工具呼叫的原始 JSON（assistant 的 tool_use / tool 的 result），M3/M4 用
    tool_calls: Mapped[str | None] = mapped_column(Text, nullable=True)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
