import { CAT, REMINDER_META } from "../lib/categories";
import {
  deriveStatus,
  durationMin,
  fmtDate,
  fmtHours,
  fmtTime,
  isToday,
  minuteOfDay,
} from "../lib/format";
import { Icon } from "../lib/icons";
import type { Event, Reminder, Task } from "../lib/types";

function freeHoursToday(todayEvents: Event[]): number {
  // 粗估 9:00–18:00 工作窗內的空檔小時數。
  const WIN_START = 9 * 60;
  const WIN_END = 18 * 60;
  // 取每個行程「落在工作窗內」的真實佔用區間（夾到窗內、丟掉窗外）
  const spans = todayEvents
    .map((e) => [
      Math.max(WIN_START, minuteOfDay(e.start_at)),
      Math.min(WIN_END, minuteOfDay(e.end_at)),
    ])
    .filter(([s, e]) => e > s)
    .sort((a, b) => a[0] - b[0]);

  // 合併重疊區間後再加總，避免兩個重疊行程被重複計算
  let busy = 0;
  let curStart = -1;
  let curEnd = -1;
  for (const [s, e] of spans) {
    if (s > curEnd) {
      busy += Math.max(0, curEnd - curStart);
      [curStart, curEnd] = [s, e];
    } else {
      curEnd = Math.max(curEnd, e);
    }
  }
  busy += Math.max(0, curEnd - curStart);

  const free = Math.max(0, WIN_END - WIN_START - busy) / 60;
  return Math.round(free * 10) / 10;
}

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
              const c = CAT[e.category];
              const state = deriveStatus(e, now);
              return (
                <div
                  key={e.id}
                  className={"s-ev" + (state === "live" ? " hot" : "") + (state === "done" ? " done" : "")}
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
              {undone.slice(0, 4).map((t) => (
                <div key={t.id} className="s-mini-task" onClick={() => onToggleTask(t)}>
                  <span className="s-check">
                    <Icon name="tick" strokeWidth={3} />
                  </span>
                  <span className="s-mt-x">{t.title}</span>
                  {t.priority === "high" && (
                    <span className="s-flag" style={{ background: "oklch(0.7 0.16 25)" }} />
                  )}
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
              {upcoming.map((r) => (
                <div key={r.id} className="s-mini-task" style={{ cursor: "default" }}>
                  <span
                    className="s-rem-ic"
                    style={{
                      width: 34,
                      height: 34,
                      borderRadius: 10,
                      background: "oklch(1 0 0 / 0.06)",
                      color: REMINDER_META[r.kind].tint,
                    }}
                  >
                    <Icon name={REMINDER_META[r.kind].icon} style={{ width: 16, height: 16 }} />
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="s-mt-x" style={{ fontWeight: 500 }}>
                      {r.title}
                    </div>
                    <div className="s-mt-due">{r.subtitle}</div>
                  </div>
                  {r.trigger_at && (
                    <span className="s-mt-due" style={{ color: "oklch(0.8 0.1 var(--acc1))" }}>
                      {fmtTime(r.trigger_at)}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
