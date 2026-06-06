import { useState } from "react";

import { AIRail } from "./components/AIRail";
import { EventDetail } from "./components/EventDetail";
import { Nav, type ViewId } from "./components/Nav";
import {
  useAddTask,
  useEvents,
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
                onAddTask={(title) => addTask.mutateAsync(title)}
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

      <AIRail />

      {detail && <EventDetail ev={detail} onClose={() => setDetail(null)} />}
    </div>
  );
}
