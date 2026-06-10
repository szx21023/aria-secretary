// 全站視覺由 :root 上四個 CSS 變數驅動（--acc1/2/3 色相 + --glow 輝光強度），
// 所有顏色都用 oklch(... var(--accN)) 算出來。這裡集中管理「主題」：
// 一組色相預設（preset）+ 一個輝光強度，套用即改變整個 app 的配色。

export interface Preset {
  id: string;
  label: string;
  /** [acc1, acc2, acc3] oklch 色相（度數），對應 --acc1/2/3 */
  acc: readonly [number, number, number];
}

// acc[0] 是主色相（Logo／導覽／按鈕／標題漸層），acc[1] 次色相，acc[2] 第三色相（多用於 glow）。
// PRESETS 是「合法 preset」的唯一真實來源：`as const` 保留字面量，PresetId 由此推導，
// 多一個少一個色票都會自動反映到型別，呼叫端打錯 id 會直接編譯失敗。
export const PRESETS = [
  { id: "aurora", label: "極光紫", acc: [300, 215, 175] }, // 預設，對齊原型
  { id: "ocean", label: "海洋藍", acc: [250, 220, 195] },
  { id: "sunset", label: "暮霞橙", acc: [40, 10, 330] },
  { id: "forest", label: "森林綠", acc: [150, 175, 125] },
  { id: "rose", label: "玫瑰粉", acc: [350, 320, 25] },
] as const satisfies readonly Preset[];

/** 合法的 preset id（封閉集合，由 PRESETS 推導）。 */
export type PresetId = (typeof PRESETS)[number]["id"];

/** 執行期守衛：把來自 localStorage 等外部來源的未知值收斂回 PresetId。 */
export function isPresetId(v: unknown): v is PresetId {
  return PRESETS.some((p) => p.id === v);
}

export interface Theme {
  preset: PresetId;
  glow: number; // 0..1
}

export const DEFAULT_THEME: Theme = { preset: "aurora", glow: 0.5 };

const STORAGE_KEY = "aria.theme";

export const clamp01 = (n: number) => Math.min(1, Math.max(0, n));

export function presetById(id: string): Preset {
  return PRESETS.find((p) => p.id === id) ?? PRESETS[0];
}

/** 把主題寫進 :root CSS 變數，畫面即時跟著變（不需重繪任何元件）。 */
export function applyTheme(theme: Theme): void {
  const p = presetById(theme.preset);
  const root = document.documentElement.style;
  root.setProperty("--acc1", String(p.acc[0]));
  root.setProperty("--acc2", String(p.acc[1]));
  root.setProperty("--acc3", String(p.acc[2]));
  root.setProperty("--glow", String(clamp01(theme.glow)));
}

export function loadTheme(): Theme {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_THEME;
    const parsed = JSON.parse(raw) as Partial<Theme>;
    return {
      // 只認仍存在的 preset id；舊版改名/移除的 id 會退回預設色，
      // 否則 SettingsPanel 會比對不到任何色票而呈現「沒選取」的死狀態。
      preset: isPresetId(parsed.preset) ? parsed.preset : DEFAULT_THEME.preset,
      glow: typeof parsed.glow === "number" ? clamp01(parsed.glow) : DEFAULT_THEME.glow,
    };
  } catch (e) {
    // localStorage 不可用或內容壞掉都退回預設，不該讓設定讀取拖垮整個 app。
    // 對齊 useChat 的慣例：壞掉的持久化資料留個 log 方便日後追（saveTheme 則刻意不 log）。
    console.error("讀取主題設定失敗，退回預設", e);
    return DEFAULT_THEME;
  }
}

export function saveTheme(theme: Theme): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(theme));
  } catch {
    /* 隱私模式等情況寫不進去就算了，主題仍會套用於本次工作階段 */
  }
}

/** 給 UI 預覽用：把一組色相組成代表性的漸層字串。 */
export function presetGradient(p: Preset): string {
  return `linear-gradient(135deg, oklch(0.72 0.18 ${p.acc[0]}), oklch(0.68 0.16 ${p.acc[1]}), oklch(0.66 0.16 ${p.acc[2]}))`;
}
