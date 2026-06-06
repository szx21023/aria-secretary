import { CAT } from "../lib/categories";
import {
  durationMin,
  fmtMonthDay,
  fmtTime,
  minuteOfDay,
  sameLocalDay,
  startOfWeekMonday,
  weekdayMon1,
} from "../lib/format";
import { Icon } from "../lib/icons";
import type { Event } from "../lib/types";

const H0 = 8;
const H1 = 21;
const PXH = 62;
const DAYS = ["一", "二", "三", "四", "五", "六", "日"];

interface Props {
  events: Event[];
  onOpenEvent: (e: Event) => void;
}

export function CalendarView({ events, onOpenEvent }: Props) {
  const now = new Date();
  const weekStart = startOfWeekMonday(now);
  const days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(weekStart);
    d.setDate(d.getDate() + i);
    return d;
  });
  const hours = Array.from({ length: H1 - H0 }, (_, i) => H0 + i);
  const nowTop = ((now.getHours() * 60 + now.getMinutes()) - H0 * 60) / 60 * PXH;
  const todayCol = weekdayMon1(now); // 1..7

  const weekEnd = new Date(days[6]);
  weekEnd.setDate(weekEnd.getDate() + 1);
  const weekNo = Math.ceil(
    ((+weekStart - +new Date(weekStart.getFullYear(), 0, 1)) / 86400000 + 1) / 7,
  );

  return (
    <div className="s-fadein" style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div className="s-head">
        <div>
          <div className="s-eyebrow">
            {weekStart.getFullYear()} 年 {weekStart.getMonth() + 1} 月
          </div>
          <h1 className="s-h1">本週</h1>
          <div className="s-h-sub">
            {fmtMonthDay(days[0])} – {fmtMonthDay(days[6])} · 第 {weekNo} 週
          </div>
        </div>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <div className="s-seg">
            <button>日</button>
            <button className="on">週</button>
            <button>月</button>
          </div>
          <div className="s-iconbtn">
            <Icon name="chevL" />
          </div>
          <div className="s-iconbtn">
            <Icon name="chevR" />
          </div>
        </div>
      </div>

      <div className="s-cal">
        <div className="s-cal-grid">
          <div className="s-cal-corner" />
          {DAYS.map((d, i) => (
            <div key={i} className={"s-cal-dh" + (i + 1 === todayCol ? " today" : "")}>
              <small>週{d}</small>
              <b>{days[i].getDate()}</b>
            </div>
          ))}
          <div className="s-cal-body">
            <div className="s-cal-hours">
              {hours.map((h) => (
                <div key={h} className="s-cal-hr">
                  {String(h).padStart(2, "0")}:00
                </div>
              ))}
            </div>
            {days.map((date, di) => {
              const dayEvents = events.filter((e) => sameLocalDay(new Date(e.start_at), date));
              return (
                <div key={di} className="s-cal-col">
                  {hours.map((h) => (
                    <div key={h} className="hrline" />
                  ))}
                  {di + 1 === todayCol && <div className="s-nowline" style={{ top: nowTop }} />}
                  {dayEvents.map((e) => {
                    const c = CAT[e.category];
                    const top = (minuteOfDay(e.start_at) - H0 * 60) / 60 * PXH;
                    const height = Math.max((durationMin(e.start_at, e.end_at) / 60) * PXH - 3, 26);
                    const done = +new Date(e.end_at) <= +now;
                    return (
                      <div
                        key={e.id}
                        className="s-cal-ev"
                        onClick={() => onOpenEvent(e)}
                        style={{
                          top,
                          height,
                          borderLeftColor: c.color,
                          background: `linear-gradient(160deg, color-mix(in oklch, ${c.color} 28%, transparent), color-mix(in oklch, ${c.color} 12%, transparent))`,
                          opacity: done ? 0.55 : 1,
                        }}
                      >
                        <b>{e.title}</b>
                        {height > 40 && (
                          <small>
                            {fmtTime(e.start_at)} · {e.location}
                          </small>
                        )}
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
