// 對應後端 Pydantic schema。datetime 為帶 offset 的 ISO 字串（UTC）。

export type EventCategory = "meeting" | "focus" | "meal" | "personal";
export type EventStatus = "scheduled" | "live" | "done";
export type TaskPriority = "high" | "medium" | "low";
export type ReminderKind = "meeting" | "birthday" | "bill" | "health";

export interface Event {
  id: string;
  title: string;
  start_at: string;
  end_at: string;
  category: EventCategory;
  location: string | null;
  attendees: number | null;
  status: EventStatus;
  note: string | null;
}

export interface Task {
  id: string;
  title: string;
  due_at: string | null;
  priority: TaskPriority | null;
  done: boolean;
}

export interface Reminder {
  id: string;
  title: string;
  subtitle: string | null;
  trigger_at: string | null;
  recurrence: string | null;
  kind: ReminderKind;
  enabled: boolean;
}

export interface ChatMessage {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
}
