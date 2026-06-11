import type { Event, Reminder, Task } from "./types";

// dev 走 vite proxy（相對路徑）；若設了 VITE_API_BASE 則打絕對位址。
const BASE = import.meta.env.VITE_API_BASE ?? "";

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${method} ${path}`);
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export const api = {
  events: () => request<Event[]>("GET", "/api/events"),

  tasks: () => request<Task[]>("GET", "/api/tasks"),
  createTask: (body: { title: string; priority?: Task["priority"] }) =>
    request<Task>("POST", "/api/tasks", body),
  updateTask: (id: string, body: Partial<Pick<Task, "title" | "done" | "priority">>) =>
    request<Task>("PATCH", `/api/tasks/${id}`, body),

  reminders: () => request<Reminder[]>("GET", "/api/reminders"),
  updateReminder: (id: string, body: Partial<Pick<Reminder, "enabled">>) =>
    request<Reminder>("PATCH", `/api/reminders/${id}`, body),
};
