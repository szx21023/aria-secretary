import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  clamp01,
  DEFAULT_THEME,
  isPresetId,
  loadTheme,
  presetById,
  PRESETS,
  saveTheme,
  type Theme,
} from "./theme";

const STORAGE_KEY = "aria.theme";

// 用記憶體版 localStorage 取代瀏覽器版，讓 loadTheme/saveTheme 可在 node 環境下測。
class MemoryStorage {
  private m = new Map<string, string>();
  getItem(k: string) {
    return this.m.has(k) ? this.m.get(k)! : null;
  }
  setItem(k: string, v: string) {
    this.m.set(k, String(v));
  }
  removeItem(k: string) {
    this.m.delete(k);
  }
  clear() {
    this.m.clear();
  }
}

beforeEach(() => {
  vi.stubGlobal("localStorage", new MemoryStorage());
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("clamp01", () => {
  it("clamps below 0 and above 1, passes through in-range", () => {
    expect(clamp01(-0.3)).toBe(0);
    expect(clamp01(1.7)).toBe(1);
    expect(clamp01(0.42)).toBe(0.42);
    expect(clamp01(0)).toBe(0);
    expect(clamp01(1)).toBe(1);
  });
});

describe("isPresetId", () => {
  it("accepts every id in PRESETS", () => {
    for (const p of PRESETS) expect(isPresetId(p.id)).toBe(true);
  });

  it("rejects unknown ids and non-string values", () => {
    expect(isPresetId("oceann")).toBe(false);
    expect(isPresetId("")).toBe(false);
    expect(isPresetId(undefined)).toBe(false);
    expect(isPresetId(null)).toBe(false);
    expect(isPresetId(42)).toBe(false);
  });
});

describe("presetById", () => {
  it("returns the matching preset", () => {
    expect(presetById("ocean").label).toBe("海洋藍");
  });

  it("falls back to the first preset (aurora) for unknown ids", () => {
    expect(presetById("does-not-exist")).toBe(PRESETS[0]);
    expect(PRESETS[0].id).toBe("aurora");
  });
});

describe("loadTheme", () => {
  it("returns DEFAULT_THEME when nothing is stored", () => {
    expect(loadTheme()).toEqual(DEFAULT_THEME);
  });

  it("round-trips a valid saved theme", () => {
    const theme: Theme = { preset: "forest", glow: 0.3 };
    saveTheme(theme);
    expect(loadTheme()).toEqual(theme);
  });

  it("falls back to the default preset when the stored id is unknown", () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ preset: "retired", glow: 0.4 }));
    const loaded = loadTheme();
    expect(loaded.preset).toBe(DEFAULT_THEME.preset);
    expect(loaded.glow).toBe(0.4); // 仍保留合法的 glow
  });

  it("clamps an out-of-range glow", () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ preset: "ocean", glow: 9 }));
    expect(loadTheme().glow).toBe(1);
  });

  it("falls back to the default glow when glow is not a number", () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ preset: "ocean", glow: "bright" }));
    expect(loadTheme().glow).toBe(DEFAULT_THEME.glow);
  });

  it("returns DEFAULT_THEME and logs when the stored JSON is corrupt", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    localStorage.setItem(STORAGE_KEY, "{not valid json");
    expect(loadTheme()).toEqual(DEFAULT_THEME);
    expect(spy).toHaveBeenCalled();
  });
});

describe("saveTheme", () => {
  it("does not throw when storage rejects the write (e.g. private mode)", () => {
    vi.spyOn(MemoryStorage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("QuotaExceededError");
    });
    expect(() => saveTheme(DEFAULT_THEME)).not.toThrow();
  });
});
