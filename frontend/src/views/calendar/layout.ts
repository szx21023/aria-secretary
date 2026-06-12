// 時間網格的像素版面計算（純函式，與 React 無關，可單測）。

export const PXH = 62; // 每小時的像素高度
const GRID_H = 24 * PXH; // 整天網格高度（00:00–24:00）

/**
 * daySegment 的分鐘區段 → 欄內的像素位置。
 * height 先套 26px 下限（太短的行程仍要點得到），top 再 clamp 讓
 * top + height ≤ 網格底——深夜短行程套了 min-height 才可能超界，
 * 順序不可對調（top 的 clamp 依賴算好的 height）。
 */
export function eventBox(seg: { startMin: number; endMin: number }): {
  top: number;
  height: number;
} {
  const height = Math.max(((seg.endMin - seg.startMin) / 60) * PXH - 3, 26);
  const top = Math.min((seg.startMin / 60) * PXH, GRID_H - height);
  return { top, height };
}
