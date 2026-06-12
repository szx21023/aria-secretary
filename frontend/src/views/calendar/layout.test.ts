import { describe, expect, it } from "vitest";

import { eventBox, PXH } from "./layout";

const GRID_H = 24 * PXH; // 1488

describe("eventBox", () => {
  it("一般行程（09:30–11:00）→ 不觸發任何 clamp", () => {
    expect(eventBox({ startMin: 570, endMin: 660 })).toEqual({
      top: 9.5 * PXH, // 589
      height: 1.5 * PXH - 3, // 90
    });
  });

  it("過短行程（10:00–10:10）→ height 補到 26px 下限", () => {
    const { top, height } = eventBox({ startMin: 600, endMin: 610 });
    expect(height).toBe(26);
    expect(top).toBe(10 * PXH); // 不在深夜，top 不受影響
  });

  it("深夜短行程（23:55–24:00）→ min-height 超界時 top clamp 回網格內", () => {
    const { top, height } = eventBox({ startMin: 1435, endMin: 1440 });
    expect(height).toBe(26);
    expect(top + height).toBe(GRID_H); // 貼齊網格底，不溢出
  });

  it("daySegment 文件允許的零長度區段 → 仍渲染 26px、不溢出網格", () => {
    const { top, height } = eventBox({ startMin: 1440, endMin: 1440 });
    expect(height).toBe(26);
    expect(top + height).toBeLessThanOrEqual(GRID_H);
  });

  it("整天區段（00:00–24:00）→ 貼齊網格、top 不為負", () => {
    const { top, height } = eventBox({ startMin: 0, endMin: 1440 });
    expect(top).toBe(0);
    expect(height).toBe(24 * PXH - 3); // 1485，留 3px 間隙
  });
});
