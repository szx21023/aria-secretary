import { useLayoutEffect, useRef } from "react";

import { catOf } from "../../lib/categories";
import { daySegment, fmtTime, sameLocalDay, WEEK_LABEL } from "../../lib/format";
import type { Event } from "../../lib/types";
import { eventBox, PXH } from "./layout";

const HOURS = Array.from({ length: 24 }, (_, i) => i); // 24 條時間列，涵蓋整天 00:00–24:00（標籤顯示 00:00–23:00）

interface Props {
  /** 要顯示的天數欄：日視圖傳 1 天、週視圖傳 7 天。 */
  days: Date[];
  events: Event[];
  now: Date;
  onOpenEvent: (e: Event) => void;
}

/**
 * 垂直時間軸網格（整天 00:00–24:00）。日視圖與週視圖共用同一份排版，
 * 差別只在傳入幾天 —— 欄數由 `days.length` 決定。
 */
export function TimeGrid({ days, events, now, onOpenEvent }: Props) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const cols = `56px repeat(${days.length}, 1fr)`;
  const todayIdx = days.findIndex((d) => sameLocalDay(d, now)); // -1 = 視圖內不含今天
  const nowTop = ((now.getHours() * 60 + now.getMinutes()) / 60) * PXH;

  // 進場／切換期間時捲到合理起點：含今天 → 現在前一小時（看得到 now-line），否則 07:00。
  const periodKey = days[0].getTime();
  useLayoutEffect(() => {
    const startHour = todayIdx >= 0 ? Math.max(0, now.getHours() - 1) : 7;
    bodyRef.current?.scrollTo({ top: startHour * PXH });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 只在期間（periodKey）改變時重新定位
  }, [periodKey]);

  return (
    <div className="s-cal">
      <div className="s-cal-grid" style={{ gridTemplateColumns: cols }}>
        <div className="s-cal-corner" />
        {days.map((d, i) => (
          <div key={i} className={"s-cal-dh" + (i === todayIdx ? " today" : "")}>
            <small>週{WEEK_LABEL[d.getDay()]}</small>
            <b>{d.getDate()}</b>
          </div>
        ))}
        <div className="s-cal-body" ref={bodyRef} style={{ gridTemplateColumns: cols }}>
          <div className="s-cal-hours">
            {HOURS.map((h) => (
              <div key={h} className="s-cal-hr">
                {String(h).padStart(2, "0")}:00
              </div>
            ))}
          </div>
          {days.map((date, di) => {
            // 跨日行程在每個重疊日各畫一段（clamp 在當天 00:00–24:00 內）
            const dayEvents = events
              .map((e) => ({ e, seg: daySegment(e.start_at, e.end_at, date) }))
              .filter((x): x is { e: Event; seg: NonNullable<typeof x.seg> } => x.seg !== null);
            return (
              <div key={di} className="s-cal-col">
                {HOURS.map((h) => (
                  <div key={h} className="hrline" />
                ))}
                {di === todayIdx && <div className="s-nowline" style={{ top: nowTop }} />}
                {dayEvents.map(({ e, seg }) => {
                  const c = catOf(e.category);
                  const { top, height } = eventBox(seg);
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
                          {fmtTime(e.start_at)}
                          {e.location && ` · ${e.location}`}
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
  );
}
