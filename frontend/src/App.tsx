import { useState } from "react";

import { Nav, type ViewId } from "./components/Nav";
import { useEvents, useHealth, useReminders, useTasks } from "./hooks/useData";
import { Placeholder } from "./views/Placeholder";

const VIEW_META: Record<ViewId, { eyebrow: string; title: string }> = {
  today: { eyebrow: "今日", title: "早安，Claire" },
  calendar: { eyebrow: "2026 年 6 月", title: "本週" },
  tasks: { eyebrow: "任務", title: "待辦事項" },
  reminders: { eyebrow: "提醒", title: "提醒與通知" },
};

export default function App() {
  const [view, setView] = useState<ViewId>("today");

  const health = useHealth();
  const events = useEvents();
  const tasks = useTasks();
  const reminders = useReminders();

  const activeReminders = (reminders.data ?? []).filter((r) => r.enabled).length;
  const undoneTasks = (tasks.data ?? []).filter((t) => !t.done).length;

  const meta = VIEW_META[view];
  const subtitle =
    view === "today"
      ? `今天有 ${events.data?.length ?? "…"} 個行程、${undoneTasks} 項待辦。`
      : "M0 — 連線後端中";

  return (
    <div className="s-app">
      <div className="s-glow s-g1" />
      <div className="s-glow s-g2" />
      <div className="s-glow s-g3" />

      <Nav view={view} onChange={setView} reminderCount={activeReminders} />

      <main className="s-main">
        <Placeholder eyebrow={meta.eyebrow} title={meta.title} subtitle={subtitle} />
      </main>

      {/* M3 會用真正的 AIRail 對話側欄取代此佔位 */}
      <aside className="s-rail">
        <div className="s-rail-h">
          <div className="s-orb" />
          <b>秘書 Aria</b>
          <small>
            {health.isLoading
              ? "連線中…"
              : health.isError
                ? "後端未連線"
                : "後端已連線 ✓"}
          </small>
        </div>
        <div className="s-thread">
          <div className="s-bub a">
            M0 骨架就緒。後端狀態：
            {health.data ? ` ${health.data.status}` : " —"}。
            已載入 {events.data?.length ?? 0} 個行程、{tasks.data?.length ?? 0} 項待辦、
            {reminders.data?.length ?? 0} 則提醒。
          </div>
          <div className="s-bub a">對話功能將於 M3 接上真 Claude API。</div>
        </div>
        <div className="s-inputbar" style={{ opacity: 0.5 }}>
          <span className="s-mic" />
          <input placeholder="（M3 啟用）輸入或說出你的需求…" disabled />
          <div className="s-send" />
        </div>
      </aside>
    </div>
  );
}
