import enum


class EventCategory(str, enum.Enum):
    meeting = "meeting"
    focus = "focus"
    meal = "meal"
    personal = "personal"


class EventStatus(str, enum.Enum):
    scheduled = "scheduled"
    live = "live"
    done = "done"


class TaskPriority(str, enum.Enum):
    high = "high"
    medium = "medium"
    low = "low"


class ReminderKind(str, enum.Enum):
    meeting = "meeting"
    birthday = "birthday"
    bill = "bill"
    health = "health"


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    system = "system"
    tool = "tool"
