import { describe, expect, it } from "vitest";

import { daySegment } from "./format";

// 用在地時間建 ISO，讓 daySegment（吃在地日界線）對齊測試裡的時刻。
// day: 2026-06-11 起算的日偏移。
const iso = (day: number, h: number, m = 0) => new Date(2026, 5, 11 + day, h, m, 0).toISOString();
const DAY0 = new Date(2026, 5, 11);
const DAY1 = new Date(2026, 5, 12);
const DAY2 = new Date(2026, 5, 13);

describe("daySegment", () => {
  it("同日行程 → 原始起迄分鐘", () => {
    expect(daySegment(iso(0, 9, 30), iso(0, 11, 0), DAY0)).toEqual({
      startMin: 9 * 60 + 30,
      endMin: 11 * 60,
    });
  });

  it("與該日無重疊 → null", () => {
    expect(daySegment(iso(0, 9, 0), iso(0, 10, 0), DAY1)).toBeNull();
    expect(daySegment(iso(1, 9, 0), iso(1, 10, 0), DAY0)).toBeNull();
  });

  it("跨午夜：首日 clamp 到 24:00、隔天從 00:00 起", () => {
    const s = iso(0, 23, 0);
    const e = iso(1, 1, 30);
    expect(daySegment(s, e, DAY0)).toEqual({ startMin: 23 * 60, endMin: 1440 });
    expect(daySegment(s, e, DAY1)).toEqual({ startMin: 0, endMin: 90 });
  });

  it("跨多日：中間整天 00:00–24:00", () => {
    const s = iso(0, 22, 0);
    const e = iso(2, 8, 0);
    expect(daySegment(s, e, DAY1)).toEqual({ startMin: 0, endMin: 1440 });
    expect(daySegment(s, e, DAY2)).toEqual({ startMin: 0, endMin: 8 * 60 });
  });

  it("恰好在午夜結束 → 不算入隔天", () => {
    const s = iso(0, 22, 0);
    const e = iso(1, 0, 0);
    expect(daySegment(s, e, DAY0)).toEqual({ startMin: 22 * 60, endMin: 1440 });
    expect(daySegment(s, e, DAY1)).toBeNull();
  });

  it("恰好在午夜開始 → 不算入前一天", () => {
    const s = iso(1, 0, 0);
    const e = iso(1, 1, 0);
    expect(daySegment(s, e, DAY0)).toBeNull();
    expect(daySegment(s, e, DAY1)).toEqual({ startMin: 0, endMin: 60 });
  });
});
