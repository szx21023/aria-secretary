import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 後端 API 預設在 :8000，dev 時用 proxy 把 /api 轉過去，
// 避免 CORS 並讓前端用相對路徑呼叫。
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
