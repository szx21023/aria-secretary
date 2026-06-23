import { useSyncExternalStore, type ReactNode } from "react";

import { getToken, subscribe } from "../lib/auth";
import { Login } from "./Login";

// 有 token 才渲染 children（主畫面）；沒有就顯示登入頁。
// 任何請求收到 401 會清掉 token（見 lib/auth.onUnauthorized），這裡即時切回登入。
export function AuthGate({ children }: { children: ReactNode }) {
  const token = useSyncExternalStore(subscribe, getToken);
  if (!token) return <Login />;
  return <>{children}</>;
}
