import { catOf, REMINDER_META } from "../lib/categories";
import { deriveStatus, durationMin, fmtDate, fmtHours, fmtTime, isToday } from "../lib/format";
import { Icon } from "../lib/icons";
import { freeHoursToday } from "../lib/schedule";
import type { Event, Reminder, Task } from "../lib/types";

interface Props {
  events: Event[];
  tasks: Task[];
  reminders: Reminder[];
  onToggleTask: (t: Task) => void;
  onOpenEvent: (e: Event) => void;
}

export function TodayView({ events, tasks, reminders, onToggleTask, onOpenEvent }: Props) {
  const now = new Date();
  const today = events
    .filter((e) => isToday(e.start_at, now))
    .sort((a, b) => +new Date(a.start_at) - +new Date(b.start_at));
  const undone = tasks.filter((t) => !t.done);
  const upcoming = reminders.filter((r) => r.enabled).slice(0, 3);
  const freeH = freeHoursToday(today);

  return (
    <div className="s-fadein">
      <div className="s-head">
        <div>
          <div className="s-eyebrow">{fmtDate(now)}</div>
          <h1 className="s-h1">
            早安，<span className="grad">Claire</span>
          </h1>
          <div className="s-h-sub">
            今天有 {today.length} 個行程、{undone.length} 項待辦。
          </div>
        </div>
        <div className="s-pills">
          <div className="s-pill">
            <b>{today.length}</b>
            <small>行程</small>
          </div>
          <div className="s-pill">
            <b>{undone.length}</b>
            <small>待辦</small>
          </div>
          <div className="s-pill">
            <b>{freeH}h</b>
            <small>空檔</small>
          </div>
        </div>
      </div>

      <div className="s-scroll">
        <div className="s-card" style={{ marginBottom: 18 }}>
          <div className="s-cardh">
            <b>今日時間軸</b>
            <small>點任一行程可查看與調整</small>
          </div>
          <div className="s-tl">
            {today.length === 0 && <div className="s-empty">今天沒有行程，好好休息 🙂</div>}
            {today.map((e) => {
              const c = catOf(e.category);
              const state = deriveStatus(e, now);
              return (
                <div
                  key={e.id}
                  className={
                    "s-ev" + (state === "live" ? " hot" : "") + (state === "done" ? " done" : "")
                  }
                  onClick={() => onOpenEvent(e)}
                >
                  <span className="s-ev-t">{fmtTime(e.start_at)}</span>
                  <span className="s-ev-bar" style={{ background: c.color }} />
                  <div className="s-ev-b">
                    <b>{e.title}</b>
                    <small>
                      {e.location}
                      {e.attendees ? ` · ${e.attendees} 人` : ""}
                      {e.note ? ` · ${e.note}` : ""}
                    </small>
                  </div>
                  {state === "live" ? (
                    <span className="s-ev-tag live">
                      <i />
                      進行中
                    </span>
                  ) : state === "done" ? (
                    <span className="s-ev-tag">已完成</span>
                  ) : (
                    <span className="s-ev-tag">
                      {c.label} · {fmtHours(durationMin(e.start_at, e.end_at))}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        <div className="s-grid2">
          <div className="s-card">
            <div className="s-cardh">
              <b>待辦重點</b>
              <small>{undone.length} 項未完成</small>
            </div>
            <div style={{ paddingBottom: 10 }}>
              {undone.length === 0 && <div className="s-empty">待辦都清空了 🎉</div>}
              {undone.slice(0, 4).map((t) => (
                <div key={t.id} className="s-mini-task" onClick={() => onToggleTask(t)}>
                  <span className="s-check">
                    <Icon name="tick" strokeWidth={3} />
                  </span>
                  <span className="s-mt-x">{t.title}</span>
                  {t.priority === "high" && <span className="s-flag hi" />}
                  {t.due_at && <span className="s-mt-due">{fmtTime(t.due_at)}</span>}
                </div>
              ))}
            </div>
          </div>

          <div className="s-card">
            <div className="s-cardh">
              <b>即將提醒</b>
              <small>{upcoming.length} 則</small>
            </div>
            <div style={{ paddingBottom: 10 }}>
              {upcoming.length === 0 && <div className="s-empty">目前沒有啟用中的提醒</div>}
              {upcoming.map((r) => (
                <div key={r.id} className="s-mini-task" style={{ cursor: "default" }}>
                  <span className="s-rem-ic sm" style={{ color: REMINDER_META[r.kind].tint }}>
                    <Icon name={REMINDER_META[r.kind].icon} />
                  </span>
                  <div className="s-mt-body">
                    <div className="s-mt-x">{r.title}</div>
                    <div className="s-mt-due">{r.subtitle}</div>
                  </div>
                  {r.trigger_at && <span className="s-mt-due acc">{fmtTime(r.trigger_at)}</span>}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
