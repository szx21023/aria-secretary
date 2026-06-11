import { useLayoutEffect, useRef, useState } from "react";

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

// 整天 00:00–24:00 全部畫出來，避免清晨／深夜行程被切在視窗外看不到；
// 預設捲動位置由 bodyRef 的 effect 控制（落在日間），其餘時段往上／下捲即可。
const H0 = 0;
const H1 = 24;
const PXH = 62;
const DAYS = ["一", "二", "三", "四", "五", "六", "日"];

interface Props {
  events: Event[];
  onOpenEvent: (e: Event) => void;
}

// weekOffset → 相對本週的標題（0=本週、-1=上週、+1=下週、其餘給相對週數）。
function weekLabel(offset: number): string {
  if (offset === 0) return "本週";
  if (offset === -1) return "上週";
  if (offset === 1) return "下週";
  return offset < 0 ? `${-offset} 週前` : `${offset} 週後`;
}

export function CalendarView({ events, onOpenEvent }: Props) {
  // 以「本週」為基準，左右箭頭調整週偏移；0 才是當前真實週。
  const [weekOffset, setWeekOffset] = useState(0);
  const isCurrentWeek = weekOffset === 0;

  const now = new Date();
  const weekStart = startOfWeekMonday(now);
  weekStart.setDate(weekStart.getDate() + weekOffset * 7);
  const days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(weekStart);
    d.setDate(d.getDate() + i);
    return d;
  });
  const hours = Array.from({ length: H1 - H0 }, (_, i) => H0 + i);
  const nowTop = ((now.getHours() * 60 + now.getMinutes()) - H0 * 60) / 60 * PXH;
  // 今日高亮／now-line 只在實際本週才有意義（其他週沒有「今天」這一欄）
  const todayCol = isCurrentWeek ? weekdayMon1(now) : 0; // 1..7，非本週為 0（不命中任何欄）

  // 近似週數＝今年第幾個 7 天區塊（從 1/1 起算，非 ISO 週，跨年邊界可能差 1）
  const weekNo = Math.ceil(
    ((+weekStart - +new Date(weekStart.getFullYear(), 0, 1)) / 86400000 + 1) / 7,
  );

  // 時間軸是整天 00:00–24:00，進場／切換週時捲到合理起點：
  // 本週捲到「現在」前一小時（看得到 now-line），其他週捲到 07:00。
  const bodyRef = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const startHour = isCurrentWeek ? Math.max(0, now.getHours() - 1) : 7;
    bodyRef.current?.scrollTo({ top: startHour * PXH });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 只在切換週時重新定位，now 取當下值即可
  }, [weekOffset]);

  return (
    <div className="s-fadein" style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div className="s-head">
        <div>
          <div className="s-eyebrow">
            {weekStart.getFullYear()} 年 {weekStart.getMonth() + 1} 月
          </div>
          <h1 className="s-h1">{weekLabel(weekOffset)}</h1>
          <div className="s-h-sub">
            {fmtMonthDay(days[0])} – {fmtMonthDay(days[6])} · 第 {weekNo} 週
          </div>
        </div>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          {/* TODO(日/月視圖)：目前僅實作週視圖。日視圖與月視圖尚未開發，
              在補上之前先不放「日」「月」按鈕，避免點了沒反應的死按鈕。 */}
          <div className="s-seg">
            <button className="on">週</button>
          </div>
          <div className="s-iconbtn" onClick={() => setWeekOffset((w) => w - 1)}>
            <Icon name="chevL" />
          </div>
          <div className="s-iconbtn" onClick={() => setWeekOffset((w) => w + 1)}>
            <Icon name="chevR" />
          </div>
        </div>
      </div>

      <div className="s-cal">
        <div className="s-cal-grid">
          <div className="s-cal-corner" />
          {DAYS.map((d, i) => (
            <div key={d} className={"s-cal-dh" + (i + 1 === todayCol ? " today" : "")}>
              <small>週{d}</small>
              <b>{days[i].getDate()}</b>
            </div>
          ))}
          <div className="s-cal-body" ref={bodyRef}>
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
