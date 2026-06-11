// 時間處理。後端傳 UTC ISO 字串（帶 Z）；前端一律用瀏覽器在地時間顯示與計算。
// （單人本機使用，假設瀏覽器時區＝使用者所在時區 Asia/Taipei。）

import type { Event, EventStatus } from "./types";

export function fmtTime(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/** 一天中的第幾分鐘（在地時間）。 */
export function minuteOfDay(iso: string): number {
  const d = new Date(iso);
  return d.getHours() * 60 + d.getMinutes();
}

/** 週幾，1=週一 … 7=週日（JS getDay 0=週日）。 */
export function weekdayMon1(d: Date): number {
  return ((d.getDay() + 6) % 7) + 1;
}

/** 行程長度（分鐘）。 */
export function durationMin(startIso: string, endIso: string): number {
  return Math.round((new Date(endIso).getTime() - new Date(startIso).getTime()) / 60000);
}

/** 是否為同一天（在地）。 */
export function sameLocalDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

export function isToday(iso: string, now: Date = new Date()): boolean {
  return sameLocalDay(new Date(iso), now);
}

/** 該日所在週的週一 00:00（在地）。 */
export function startOfWeekMonday(d: Date): Date {
  const monday = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  monday.setDate(monday.getDate() - (weekdayMon1(d) - 1));
  return monday;
}

/** 由真實時間推導行程狀態（live / done / scheduled），取代後端寫死的狀態。 */
export function deriveStatus(ev: Event, now: Date = new Date()): EventStatus {
  const start = new Date(ev.start_at).getTime();
  const end = new Date(ev.end_at).getTime();
  const t = now.getTime();
  if (t >= end) return "done";
  if (t >= start) return "live";
  return "scheduled";
}

/** 「6/5」式日期。 */
export function fmtMonthDay(d: Date): string {
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

const WEEK_LABEL = ["日", "一", "二", "三", "四", "五", "六"];

/** 「6月5日 · 星期五」式日期。 */
export function fmtDate(d: Date): string {
  return `${d.getMonth() + 1}月${d.getDate()}日 · 星期${WEEK_LABEL[d.getDay()]}`;
}

/** 分鐘數 → 「0.5h」式時長標籤。 */
export function fmtHours(minutes: number): string {
  return `${Math.round((minutes / 60) * 10) / 10}h`;
}
