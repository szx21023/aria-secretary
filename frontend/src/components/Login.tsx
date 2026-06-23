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
      const data = (await res.json()) as { token?: unknown };
      if (typeof data.token !== "string" || !data.token) {
        // 回應異常（缺 token / 非字串）：別讓 undefined 被存成 token 造成登入彈跳迴圈
        setErr("登入回應異常，請稍後再試。");
        return;
      }
      setToken(data.token);
    } catch (e) {
      console.error("登入請求失敗", e);
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
          placeholder="密碼（限英數與符號）"
          value={pw}
          autoFocus
          // 密碼限可見 ASCII（0x20–0x7E）：直接濾掉中文/emoji/控制字元，後端也會再擋一次
          onChange={(e) => setPw(e.target.value.replace(/[^\x20-\x7E]/g, ""))}
        />
        {err && <div className="auth-err">{err}</div>}
        <button className="s-btn primary auth-btn" type="submit" disabled={busy || !pw}>
          {busy ? "登入中…" : "登入"}
        </button>
      </form>
    </div>
  );
}
