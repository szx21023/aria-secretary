import { useState, type FormEvent } from "react";

import { setToken } from "../lib/auth";

const BASE = import.meta.env.VITE_API_BASE ?? "";

// 登入頁：輸入密碼換 Bearer token。成功後 setToken → AuthGate 切換到主畫面。
export function Login() {
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!pw || busy) return;
    setBusy(true);
    setErr("");
    try {
      const res = await fetch(`${BASE}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password: pw }),
      });
      if (res.status === 401) {
        setErr("密碼錯誤");
        return;
      }
      if (!res.ok) {
        setErr("登入服務暫時無法使用，請稍後再試。");
        return;
      }
      const { token } = (await res.json()) as { token: string };
      setToken(token);
    } catch {
      setErr("連線失敗，請稍後再試。");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="s-pop-back">
      <form className="s-pop s-fadein auth-card" onSubmit={submit}>
        <div className="s-eyebrow">Aria</div>
        <h3>登入</h3>
        <p className="auth-sub">這是私人秘書，請輸入密碼。</p>
        <input
          className="auth-input"
          type="password"
          placeholder="密碼"
          value={pw}
          autoFocus
          onChange={(e) => setPw(e.target.value)}
        />
        {err && <div className="auth-err">{err}</div>}
        <button className="s-btn primary auth-btn" type="submit" disabled={busy || !pw}>
          {busy ? "登入中…" : "登入"}
        </button>
      </form>
    </div>
  );
}
