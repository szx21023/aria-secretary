// 行程時間計算（純函式，不依賴 React／DOM，便於單元測試）。

import { minuteOfDay } from "./format";
import type { Event } from "./types";

/** 工作窗（在地時間，分鐘）：09:00–18:00。空檔估算只看這個區間內。 */
const WORK_WINDOW_START = 9 * 60;
const WORK_WINDOW_END = 18 * 60;

/**
 * 粗估某日在 09:00–18:00 工作窗內的空檔小時數（四捨五入到小數一位）。
 *
 * 作法：取每個行程落在工作窗內的真實佔用區間（夾到窗內、丟掉窗外），
 * 合併重疊區間後加總忙碌分鐘數，避免兩個重疊行程被重複計算，再以
 * 窗長扣掉忙碌時間。
 */
export function freeHoursToday(todayEvents: Event[]): number {
  const spans = todayEvents
    .map((e): [number, number] => [
      Math.max(WORK_WINDOW_START, minuteOfDay(e.start_at)),
      Math.min(WORK_WINDOW_END, minuteOfDay(e.end_at)),
    ])
    .filter(([s, e]) => e > s)
    .sort((a, b) => a[0] - b[0]);

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

  const free = Math.max(0, WORK_WINDOW_END - WORK_WINDOW_START - busy) / 60;
  return Math.round(free * 10) / 10;
}
