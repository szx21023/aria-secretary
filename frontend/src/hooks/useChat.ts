import { useCallback, useEffect, useState } from "react";

const BASE = import.meta.env.VITE_API_BASE ?? "";

const RETRY_MSG = "抱歉，我剛剛沒處理好，可以再說一次嗎？";
const CONNECTION_MSG = "抱歉，連線出了點問題，請稍後再試。";

export interface Bubble {
  who: "a" | "u";
  text: string;
}

interface HistoryRow {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
}

// 與後端 schemas.chat.ChatEvent 對應的線上協定
type ChatEvent =
  | { type: "delta"; text: string }
  | { type: "tool"; name: string }
  | { type: "done"; text: string }
  | { type: "error"; message: string };

export function useChat() {
  const [messages, setMessages] = useState<Bubble[]>([]);
  const [thinking, setThinking] = useState(false);

  // 載入歷史對話
  useEffect(() => {
    fetch(`${BASE}/api/chat/history`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((rows: HistoryRow[]) =>
        setMessages(rows.map((m) => ({ who: m.role === "user" ? "u" : "a", text: m.content }))),
      )
      .catch((e) => console.error("載入對話歷史失敗", e));
  }, []);

  // 把片段寫進「當前 assistant 泡泡」。是否為本回合第一塊，純粹由 state 判斷：
  // 最後一則若是 user（剛送出的提問）就新建 assistant 泡泡，否則接續。
  // 這樣 updater 完全是純函式 —— 不依賴外部旗標，避免 React 18 StrictMode／render
  // 時序造成旗標已翻轉、片段接錯到 user 泡泡的競態。
  const appendAssistant = (chunk: string) =>
    setMessages((m) => {
      const last = m[m.length - 1];
      if (!last || last.who === "u") return [...m, { who: "a", text: chunk }];
      const next = m.slice();
      next[next.length - 1] = { who: "a", text: last.text + chunk };
      return next;
    });

  // 失敗訊息：已有部分回覆就空兩行接在後面，避免蓋掉使用者已看到的內容
  const fail = (msg: string) =>
    setMessages((m) => {
      const last = m[m.length - 1];
      if (!last || last.who === "u") return [...m, { who: "a", text: msg }];
      const next = m.slice();
      next[next.length - 1] = { who: "a", text: last.text ? `${last.text}\n\n${msg}` : msg };
      return next;
    });

  const send = useCallback(
    async (raw: string) => {
      const text = raw.trim();
      if (!text || thinking) return;
      setMessages((m) => [...m, { who: "u", text }]);
      setThinking(true);

      try {
        const res = await fetch(`${BASE}/api/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text }),
        });
        if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          // SSE 以空行分隔；最後一段可能是被切斷的半截 frame，留回 buf 等下個 chunk 拼完整
          const parts = buf.split("\n\n");
          buf = parts.pop() ?? "";
          for (const part of parts) {
            const line = part.trim();
            if (!line.startsWith("data:")) continue;
            let ev: ChatEvent;
            try {
              ev = JSON.parse(line.slice(5).trim());
            } catch (e) {
              console.error("無法解析 SSE frame", line, e); // 單行壞掉不該拆掉整個串流
              continue;
            }
            if (ev.type === "delta") appendAssistant(ev.text);
            else if (ev.type === "error") {
              console.error("對話錯誤：", ev.message);
              fail(RETRY_MSG);
            }
            // tool / done：無需額外 UI 動作（thinking 狀態已處理）
          }
        }
      } catch (e) {
        console.error("對話連線失敗", e);
        fail(CONNECTION_MSG);
      } finally {
        setThinking(false);
      }
    },
    [thinking],
  );

  return { messages, thinking, send };
}
