// 登入 token 的單一真相來源：存 localStorage，並提供訂閱讓 AuthGate 在登入/登出時切畫面。
// 單人自用採 Bearer token（非 httpOnly cookie）；XSS 風險已知並接受。

const KEY = "aria_token";
const listeners = new Set<() => void>();

export function getToken(): string | null {
  // 空字串視為未登入，避免送出 "Bearer "（空 token）造成登入↔登出彈跳
  return localStorage.getItem(KEY) || null;
}

export function setToken(token: string): void {
  if (!token) return; // 不存空值；呼叫端應已驗證 token 非空字串
  localStorage.setItem(KEY, token);
  emit();
}

export function clearToken(): void {
  localStorage.removeItem(KEY);
  emit();
}

// 給每個 API 請求帶上的授權標頭（沒 token 就回空物件）。
export function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

// 任何請求收到 401 時呼叫：清掉 token → AuthGate 自動切回登入頁。
export function onUnauthorized(): void {
  if (getToken()) clearToken();
}

// 給 useSyncExternalStore 訂閱 token 變化用。
export function subscribe(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function emit(): void {
  listeners.forEach((fn) => fn());
}
