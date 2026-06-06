import type { Event, Reminder, Task } from "./types";

// dev 走 vite proxy（相對路徑）；若設了 VITE_API_BASE 則打絕對位址。
const BASE = import.meta.env.VITE_API_BASE ?? "";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${path}`);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => get<{ status: string; app: string }>("/api/health"),
  events: () => get<Event[]>("/api/events"),
  tasks: () => get<Task[]>("/api/tasks"),
  reminders: () => get<Reminder[]>("/api/reminders"),
};
