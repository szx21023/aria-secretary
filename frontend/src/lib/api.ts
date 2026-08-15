import { authHeaders, onUnauthorized } from "./auth";
import type { Event, Life, Reminder, Task } from "./types";

// dev 走 vite proxy（相對路徑）；若設了 VITE_API_BASE 則打絕對位址。
const BASE = import.meta.env.VITE_API_BASE ?? "";

// 只給日期的里程碑排在當天這個時間、長度一小時，與後端 AI 工具的預設一致
// （app/ai/executor.py 的 MILESTONE_DEFAULT_TIME / MILESTONE_DURATION_MIN）。
const MILESTONE_DEFAULT_TIME = "09:00";
const MILESTONE_DURATION_MIN = 60;

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      ...authHeaders(),
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  // 401：token 失效/未登入 → 登出（AuthGate 切回登入頁），不再往下當一般錯誤吞掉
  if (res.status === 401) {
    onUnauthorized();
    throw new Error(`401 未授權 — ${method} ${path}`);
  }
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

  life: () => request<Life>("GET", "/api/life"),
  saveLife: (body: { birthday: string; life_expectancy: number }) =>
    request<Life>("PUT", "/api/life", body),

  // 里程碑就是標了 is_milestone 的行程，走既有的 events API。
  createMilestone: (body: { title: string; target_date: string }) => {
    // `YYYY-MM-DDTHH:mm` 不帶時區時 JS 視為在地時間，toISOString 才會轉出正確的 UTC 瞬間。
    // 直接送在地字串會被後端當成 UTC（見 schemas/types.py），日期會位移。
    const start = new Date(`${body.target_date}T${MILESTONE_DEFAULT_TIME}`);
    const end = new Date(start.getTime() + MILESTONE_DURATION_MIN * 60_000);
    return request<Event>("POST", "/api/events", {
      title: body.title,
      start_at: start.toISOString(),
      end_at: end.toISOString(),
      category: "personal",
      is_milestone: true,
    });
  },
};
