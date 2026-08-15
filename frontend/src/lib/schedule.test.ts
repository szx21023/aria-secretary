import { describe, expect, it } from "vitest";

import { freeHoursToday } from "./schedule";
import type { Event } from "./types";

// 只有 start_at/end_at 影響計算；其餘欄位給最小合法值。
// 用在地時間建 ISO，讓 minuteOfDay（吃在地時）對齊測試裡的時刻。
function ev(startHHMM: string, endHHMM: string): Event {
  const iso = (hhmm: string) => {
    const [h, m] = hhmm.split(":").map(Number);
    const d = new Date(2026, 5, 11, h, m, 0); // 2026-06-11 在地時間
    return d.toISOString();
  };
  return {
    id: `${startHHMM}-${endHHMM}`,
    title: "x",
    start_at: iso(startHHMM),
    end_at: iso(endHHMM),
    category: "meeting",
    location: null,
    attendees: null,
    status: "scheduled",
    note: null,
    is_milestone: false,
  };
}

describe("freeHoursToday", () => {
  it("空行程 → 整個工作窗 9 小時都是空檔", () => {
    expect(freeHoursToday([])).toBe(9);
  });

  it("單一行程扣掉對應時數", () => {
    expect(freeHoursToday([ev("10:00", "11:00")])).toBe(8);
  });

  it("重疊行程只計一次忙碌時間（不重複扣）", () => {
    // 10:00–12:00 與 11:00–13:00 重疊，合併後忙碌 3 小時 → 空檔 6
    expect(freeHoursToday([ev("10:00", "12:00"), ev("11:00", "13:00")])).toBe(6);
  });

  it("亂序輸入仍正確合併（驗 .sort 不可省）", () => {
    // 同上一組重疊區間，但故意把較晚開始的放前面 → 仍應得 6
    expect(freeHoursToday([ev("11:00", "13:00"), ev("10:00", "12:00")])).toBe(6);
  });

  it("剛好相鄰（前段結束＝後段開始）視為連續忙碌", () => {
    // 09:00–10:00 與 10:00–11:00 邊界相接，合併為 2 小時忙碌 → 空檔 7
    expect(freeHoursToday([ev("09:00", "10:00"), ev("10:00", "11:00")])).toBe(7);
  });

  it("非整數結果會四捨五入到小數一位", () => {
    // 忙碌 20 分 → 空檔 (540-20)/60 = 8.666… → 8.7
    expect(freeHoursToday([ev("10:00", "10:20")])).toBe(8.7);
  });

  it("相鄰不重疊的行程各自扣時", () => {
    expect(freeHoursToday([ev("09:00", "10:00"), ev("11:00", "12:00")])).toBe(7);
  });

  it("超出工作窗的部分夾掉，只算窗內佔用", () => {
    // 07:00–10:00 只有 09:00–10:00（1h）落在窗內 → 空檔 8
    expect(freeHoursToday([ev("07:00", "10:00")])).toBe(8);
  });

  it("完全在工作窗外的行程不影響空檔", () => {
    expect(freeHoursToday([ev("19:00", "20:00")])).toBe(9);
  });

  it("塞滿整個工作窗 → 空檔 0", () => {
    expect(freeHoursToday([ev("09:00", "18:00")])).toBe(0);
  });

  it("超出工作窗兩端的單一行程仍夾回 0（不會出現負空檔）", () => {
    // 08:00–20:00 完全覆蓋並超出 09:00–18:00，夾回窗內 = 滿載 → 空檔 0（非負）
    expect(freeHoursToday([ev("08:00", "20:00")])).toBe(0);
  });
});
