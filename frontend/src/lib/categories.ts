import type { IconName } from "./icons";
import type { EventCategory, ReminderKind } from "./types";

// 行程分類 → 標籤與色（oklch，沿用原型 data.jsx）
export const CAT: Record<EventCategory, { label: string; color: string }> = {
  meeting: { label: "會議", color: "oklch(0.78 0.14 290)" },
  focus: { label: "專注", color: "oklch(0.72 0.13 215)" },
  meal: { label: "用餐", color: "oklch(0.78 0.1 60)" },
  personal: { label: "個人", color: "oklch(0.75 0.13 150)" },
};

// 後端若新增分類但前端尚未跟上部署，用中性色降級顯示，避免整個視圖崩潰。
const FALLBACK_CAT = { label: "其他", color: "oklch(0.7 0 0)" };
export function catOf(category: string): { label: string; color: string } {
  return CAT[category as EventCategory] ?? FALLBACK_CAT;
}

// 提醒種類 → 圖示名與色
export const REMINDER_META: Record<ReminderKind, { icon: IconName; tint: string }> = {
  meeting: { icon: "bell", tint: "oklch(0.7 0.13 290)" },
  birthday: { icon: "cake", tint: "oklch(0.72 0.13 350)" },
  bill: { icon: "card", tint: "oklch(0.74 0.1 60)" },
  health: { icon: "heart", tint: "oklch(0.72 0.13 150)" },
};
