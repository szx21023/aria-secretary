// 時間格式化。後端傳 UTC ISO 字串，這裡用瀏覽器本地時區顯示。

const TZ = "Asia/Taipei";

export function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("zh-TW", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: TZ,
  });
}

export function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("zh-TW", {
    month: "long",
    day: "numeric",
    weekday: "long",
    timeZone: TZ,
  });
}

export function durationMin(startIso: string, endIso: string): number {
  return Math.round((new Date(endIso).getTime() - new Date(startIso).getTime()) / 60000);
}
