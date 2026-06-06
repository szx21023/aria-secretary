import { useState } from "react";

import { EventDetail } from "./components/EventDetail";
import { Nav, type ViewId } from "./components/Nav";
import {
  useAddTask,
  useEvents,
  useHealth,
  useReminders,
  useTasks,
  useToggleReminder,
  useToggleTask,
} from "./hooks/useData";
import type { Event } from "./lib/types";
import { CalendarView } from "./views/CalendarView";
import { RemindersView } from "./views/RemindersView";
import { TasksView } from "./views/TasksView";
import { TodayView } from "./views/TodayView";

export default function App() {
  const [view, setView] = useState<ViewId>("today");
  const [detail, setDetail] = useState<Event | null>(null);

  const health = useHealth();
  const events = useEvents();
  const tasks = useTasks();
  const reminders = useReminders();

  const addTask = useAddTask();
  const toggleTask = useToggleTask();
  const toggleReminder = useToggleReminder();

  const evList = events.data ?? [];
  const taskList = tasks.data ?? [];
  const reminderList = reminders.data ?? [];
  const activeReminders = reminderList.filter((r) => r.enabled).length;

  const loading = events.isLoading || tasks.isLoading || reminders.isLoading;
  const error = events.isError || tasks.isError || reminders.isError;

  return (
    <div className="s-app">
      <div className="s-glow s-g1" />
      <div className="s-glow s-g2" />
      <div className="s-glow s-g3" />

      <Nav view={view} onChange={setView} reminderCount={activeReminders} />

      <main className="s-main">
        {error ? (
          <div className="s-fadein" style={{ padding: 40 }}>
            <div className="s-card">
              <div className="s-empty">無法連線後端 — 請確認 API 是否啟動於 :8000</div>
            </div>
          </div>
        ) : loading ? (
          <div className="s-fadein" style={{ padding: 40 }}>
            <div className="s-card">
              <div className="s-empty">載入中…</div>
            </div>
          </div>
        ) : (
          <>
            {view === "today" && (
              <TodayView
                events={evList}
                tasks={taskList}
                reminders={reminderList}
                onToggleTask={(t) => toggleTask.mutate(t)}
                onOpenEvent={setDetail}
              />
            )}
            {view === "calendar" && <CalendarView events={evList} onOpenEvent={setDetail} />}
            {view === "tasks" && (
              <TasksView
                tasks={taskList}
                onToggleTask={(t) => toggleTask.mutate(t)}
                onAddTask={(title) => addTask.mutate(title)}
              />
            )}
            {view === "reminders" && (
              <RemindersView
                reminders={reminderList}
                onToggleReminder={(r) => toggleReminder.mutate({ id: r.id, enabled: r.enabled })}
              />
            )}
          </>
        )}
      </main>

      {/* M3 會用真正的 AIRail 對話側欄取代此佔位 */}
      <aside className="s-rail">
        <div className="s-rail-h">
          <div className="s-orb" />
          <b>秘書 Aria</b>
          <small>
            {health.isLoading ? "連線中…" : health.isError ? "後端未連線" : "隨時為你安排"}
          </small>
        </div>
        <div className="s-thread">
          <div className="s-bub a">
            早安 ☀️ 今天有 {evList.filter((e) => new Date(e.start_at).toDateString() === new Date().toDateString()).length} 個行程、
            {taskList.filter((t) => !t.done).length} 項待辦。需要我幫你安排什麼嗎？
          </div>
          <div className="s-bub a">對話功能將於 M3 接上真 Claude API。</div>
        </div>
        <div className="s-inputbar" style={{ opacity: 0.5 }}>
          <span className="s-mic" />
          <input placeholder="（M3 啟用）輸入或說出你的需求…" disabled />
          <div className="s-send" />
        </div>
      </aside>

      {detail && <EventDetail ev={detail} onClose={() => setDetail(null)} />}
    </div>
  );
}
