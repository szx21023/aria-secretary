import { createContext, useContext, useLayoutEffect, useState, type ReactNode } from "react";

import {
  applyTheme,
  clamp01,
  DEFAULT_THEME,
  loadTheme,
  saveTheme,
  type PresetId,
  type Theme,
} from "./theme";

interface ThemeApi {
  theme: Theme;
  setPreset: (id: PresetId) => void;
  setGlow: (glow: number) => void;
  reset: () => void;
}

const ThemeCtx = createContext<ThemeApi | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  // 初值就從 localStorage 讀，render 前 useLayoutEffect 立刻套用，避免閃一下預設色。
  const [theme, setTheme] = useState<Theme>(loadTheme);

  useLayoutEffect(() => {
    applyTheme(theme);
    saveTheme(theme);
  }, [theme]);

  const api: ThemeApi = {
    theme,
    setPreset: (preset) => setTheme((t) => ({ ...t, preset })),
    // 在唯一的寫入點就夾住 0..1，讓 theme.glow 對所有讀者都成立（不只 applyTheme）
    setGlow: (glow) => setTheme((t) => ({ ...t, glow: clamp01(glow) })),
    reset: () => setTheme(DEFAULT_THEME),
  };

  return <ThemeCtx.Provider value={api}>{children}</ThemeCtx.Provider>;
}

export function useTheme(): ThemeApi {
  const ctx = useContext(ThemeCtx);
  if (!ctx) throw new Error("useTheme 必須在 <ThemeProvider> 內使用");
  return ctx;
}
