import { useState } from "react";

import { fmtMonthDay, startOfWeekMonday, WEEK_LABEL } from "../lib/format";
import { Icon } from "../lib/icons";
import type { Event } from "../lib/types";
import { MonthGrid } from "./calendar/MonthGrid";
import { TimeGrid } from "./calendar/TimeGrid";

type ViewMode = "day" | "week" | "month";

const MODES: { id: ViewMode; label: string }[] = [
  { id: "day", label: "日" },
  { id: "week", label: "週" },
  { id: "month", label: "月" },
];

const DAY_MS = 86_400_000;
const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate());

// header 標題用的相對標籤（以「今天」為基準）
function dayLabel(anchor: Date, today: Date): string {
  const diff = Math.round((+startOfDay(anchor) - +startOfDay(today)) / DAY_MS);
  if (diff === 0) return "今天";
  if (diff === 1) return "明天";
  if (diff === -1) return "昨天";
  return `${anchor.getMonth() + 1} 月 ${anchor.getDate()} 日`;
}
function weekLabel(anchor: Date, today: Date): string {
  const off = Math.round((+startOfWeekMonday(anchor) - +startOfWeekMonday(today)) / (7 * DAY_MS));
  if (off === 0) return "本週";
  if (off === -1) return "上週";
  if (off === 1) return "下週";
  return off < 0 ? `${-off} 週前` : `${off} 週後`;
}
function monthLabel(anchor: Date, today: Date): string {
  const off =
    (anchor.getFullYear() - today.getFullYear()) * 12 + (anchor.getMonth() - today.getMonth());
  if (off === 0) return "本月";
  if (off === -1) return "上月";
  if (off === 1) return "下月";
  return `${anchor.getFullYear()} 年 ${anchor.getMonth() + 1} 月`;
}

interface Props {
  events: Event[];
  onOpenEvent: (e: Event) => void;
}

export function CalendarView({ events, onOpenEvent }: Props) {
  const now = new Date();
  const [mode, setMode] = useState<ViewMode>("week");
  // anchor 為「目前檢視的基準日」（在地午夜）。日/週/月三模式都從它推算要顯示的範圍。
  const [anchor, setAnchor] = useState<Date>(() => startOfDay(new Date()));

  // 左右箭頭依當前模式換日／週／月
  const shift = (dir: 1 | -1) =>
    setAnchor((a) => {
      const d = new Date(a);
      if (mode === "day") d.setDate(d.getDate() + dir);
      else if (mode === "week") d.setDate(d.getDate() + dir * 7);
      else d.setMonth(d.getMonth() + dir);
      return d;
    });

  const weekDays = Array.from({ length: 7 }, (_, i) => {
    const d = startOfWeekMonday(anchor);
    d.setDate(d.getDate() + i);
    return d;
  });

  // header 三段依模式變化
  const eyebrow = `${anchor.getFullYear()} 年 ${anchor.getMonth() + 1} 月`;
  let title: string;
  let sub: string;
  if (mode === "day") {
    title = dayLabel(anchor, now);
    sub = `${anchor.getMonth() + 1}月${anchor.getDate()}日 · 星期${WEEK_LABEL[anchor.getDay()]}`;
  } else if (mode === "week") {
    const weekNo = Math.ceil(
      ((+startOfWeekMonday(anchor) - +new Date(anchor.getFullYear(), 0, 1)) / DAY_MS + 1) / 7,
    );
    title = weekLabel(anchor, now);
    sub = `${fmtMonthDay(weekDays[0])} – ${fmtMonthDay(weekDays[6])} · 第 ${weekNo} 週`;
  } else {
    const count = events.filter((e) => {
      const d = new Date(e.start_at);
      return d.getMonth() === anchor.getMonth() && d.getFullYear() === anchor.getFullYear();
    }).length;
    title = monthLabel(anchor, now);
    sub = `本月 ${count} 個行程`;
  }

  return (
    <div className="s-fadein" style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div className="s-head">
        <div>
          <div className="s-eyebrow">{eyebrow}</div>
          <h1 className="s-h1">{title}</h1>
          <div className="s-h-sub">{sub}</div>
        </div>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <div className="s-seg">
            {MODES.map((m) => (
              <button
                key={m.id}
                className={mode === m.id ? "on" : ""}
                onClick={() => setMode(m.id)}
              >
                {m.label}
              </button>
            ))}
          </div>
          <div className="s-iconbtn" onClick={() => shift(-1)}>
            <Icon name="chevL" />
          </div>
          <div className="s-iconbtn" onClick={() => shift(1)}>
            <Icon name="chevR" />
          </div>
        </div>
      </div>

      {mode === "month" ? (
        <MonthGrid
          anchor={anchor}
          events={events}
          now={now}
          onOpenEvent={onOpenEvent}
          // 點某天 → 切到該天的日視圖（同 Google 日曆習慣）
          onPickDay={(d) => {
            setAnchor(startOfDay(d));
            setMode("day");
          }}
        />
      ) : (
        <TimeGrid
          days={mode === "day" ? [anchor] : weekDays}
          events={events}
          now={now}
          onOpenEvent={onOpenEvent}
        />
      )}
    </div>
  );
}
