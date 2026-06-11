import { catOf } from "../../lib/categories";
import { sameLocalDay, startOfWeekMonday } from "../../lib/format";
import type { Event } from "../../lib/types";

const MAX_CHIPS = 3; // 每格最多顯示幾條，其餘收合成「+N 更多」
const MON_HEADERS = ["一", "二", "三", "四", "五", "六", "日"]; // 週一起始
const CELLS = 42; // 6 週 × 7 天，足以容納任何月份的排版

interface Props {
  /** 目標月份中的任一天（決定要顯示哪個月）。 */
  anchor: Date;
  events: Event[];
  now: Date;
  onOpenEvent: (e: Event) => void;
  onPickDay: (d: Date) => void;
}

/** 月視圖：6×7 格，每格顯示日期 + 當天行程文字小條（超過 MAX_CHIPS 收合）。 */
export function MonthGrid({ anchor, events, now, onOpenEvent, onPickDay }: Props) {
  const month = anchor.getMonth();
  const gridStart = startOfWeekMonday(new Date(anchor.getFullYear(), month, 1));
  const cells = Array.from({ length: CELLS }, (_, i) => {
    const d = new Date(gridStart);
    d.setDate(d.getDate() + i);
    return d;
  });

  return (
    <div className="s-cal-month">
      <div className="s-cal-mhead">
        {MON_HEADERS.map((d) => (
          <div key={d} className="s-cal-mh">
            週{d}
          </div>
        ))}
      </div>
      <div className="s-cal-mbody">
        {cells.map((date, i) => {
          const dim = date.getMonth() !== month; // 非當月（前後月補滿格）淡化
          const isToday = sameLocalDay(date, now);
          const dayEvents = events
            .filter((e) => sameLocalDay(new Date(e.start_at), date))
            .sort((a, b) => +new Date(a.start_at) - +new Date(b.start_at));
          const shown = dayEvents.slice(0, MAX_CHIPS);
          const extra = dayEvents.length - shown.length;
          return (
            <div
              key={i}
              className={"s-cal-cell" + (dim ? " dim" : "") + (isToday ? " today" : "")}
              onClick={() => onPickDay(date)}
            >
              <span className="s-cal-daynum">{date.getDate()}</span>
              {shown.map((e) => {
                const c = catOf(e.category);
                return (
                  <div
                    key={e.id}
                    className="s-cal-chip"
                    title={e.title}
                    onClick={(ev) => {
                      ev.stopPropagation(); // 別讓點小條冒泡成「點整格 → 切日視圖」
                      onOpenEvent(e);
                    }}
                    style={{
                      borderLeftColor: c.color,
                      background: `color-mix(in oklch, ${c.color} 18%, transparent)`,
                    }}
                  >
                    {e.title}
                  </div>
                );
              })}
              {extra > 0 && <div className="s-cal-more">+{extra} 更多</div>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
