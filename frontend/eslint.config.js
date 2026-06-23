import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import prettier from "eslint-config-prettier";

// 非型別感知(type-aware)設定:型別檢查交給 tsc,ESLint 專注品質規則,跑得快、噪音低。
export default tseslint.config(
  { ignores: ["dist", "coverage", "vite.config.js", "vite.config.d.ts"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      // 只開兩條經典 hooks 規則;v7 的 React-Compiler 系列規則太激進,先不啟用
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
    },
  },
  // 測試檔(vitest)額外給 node globals
  {
    files: ["**/*.test.{ts,tsx}"],
    languageOptions: { globals: globals.node },
  },
  // 一律放最後:關掉與 Prettier 衝突的格式類規則
  prettier,
);
