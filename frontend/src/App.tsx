import { useState, type ReactNode } from "react";

import { AIRail } from "./components/AIRail";
import { EventDetail } from "./components/EventDetail";
import { Nav, type ViewId } from "./components/Nav";
import { SettingsPanel } from "./components/SettingsPanel";
import {
  useAddMilestone,
  useAddTask,
  useEvents,
  useLife,
  useReminders,
  useSaveLife,
  useTasks,
  useToggleReminder,
  useToggleTask,
} from "./hooks/useData";
import type { Event } from "./lib/types";
import { CalendarView } from "./views/CalendarView";
import { LifeView } from "./views/LifeView";
import { RemindersView } from "./views/RemindersView";
import { TasksView } from "./views/TasksView";
import { TodayView } from "./views/TodayView";

/** 置中卡片，用於載入中／錯誤等整頁佔位狀態。 */
function CenterCard({ children }: { children: ReactNode }) {
  return (
    <div className="s-fadein" style={{ padding: 40 }}>
      <div className="s-card">
        <div className="s-empty">{children}</div>
      </div>
    </div>
  );
}

export default function App() {
  const [view, setView] = useState<ViewId>("today");
  const [detail, setDetail] = useState<Event | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const events = useEvents();
  const tasks = useTasks();
  const reminders = useReminders();
  // 人生倒數不參與下方的整頁 loading 閘門：它與行程/待辦無關，
  // 自己在 LifeView 內處理未載入狀態，免得拖慢其他視圖的首屏。
  const life = useLife();

  const addTask = useAddTask();
  const saveLife = useSaveLife();
  const addMilestone = useAddMilestone();
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

      <Nav
        view={view}
        onChange={setView}
        reminderCount={activeReminders}
        onOpenSettings={() => setSettingsOpen(true)}
      />

      <main className="s-main">
        {error ? (
          <CenterCard>無法連線後端 — 請確認 API 是否啟動於 :8000</CenterCard>
        ) : loading ? (
          <CenterCard>載入中…</CenterCard>
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
            {view === "life" && (
              <LifeView
                life={life.data}
                onSave={(body) => saveLife.mutateAsync(body)}
                saving={saveLife.isPending}
                onAddMilestone={(body) => addMilestone.mutateAsync(body)}
                error={life.isError}
              />
            )}
          </>
        )}
      </main>

      <AIRail />

      {detail && <EventDetail ev={detail} onClose={() => setDetail(null)} />}
      {settingsOpen && <SettingsPanel onClose={() => setSettingsOpen(false)} />}
    </div>
  );
}
