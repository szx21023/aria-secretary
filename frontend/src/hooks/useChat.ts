import { useCallback, useEffect, useState } from "react";

const BASE = import.meta.env.VITE_API_BASE ?? "";

export interface Bubble {
  who: "a" | "u";
  text: string;
}

interface HistoryRow {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
}

export function useChat() {
  const [messages, setMessages] = useState<Bubble[]>([]);
  const [thinking, setThinking] = useState(false);

  // 載入歷史對話
  useEffect(() => {
    fetch(`${BASE}/api/chat/history`)
      .then((r) => (r.ok ? r.json() : []))
      .then((rows: HistoryRow[]) =>
        setMessages(rows.map((m) => ({ who: m.role === "user" ? "u" : "a", text: m.content }))),
      )
      .catch(() => {});
  }, []);

  // 注意：setMessages 的 updater 必須是純函式（React 18 StrictMode 會重複呼叫），
  // 所以「是否已建立 assistant 泡泡」的旗標放在 updater 外面，不在裡面做副作用。
  const appendToAssistant = (text: string) =>
    setMessages((m) => {
      const next = m.slice();
      next[next.length - 1] = { who: "a", text: next[next.length - 1].text + text };
      return next;
    });

  const replaceAssistant = (text: string) =>
    setMessages((m) => {
      const next = m.slice();
      next[next.length - 1] = { who: "a", text };
      return next;
    });

  const send = useCallback(
    async (raw: string) => {
      const text = raw.trim();
      if (!text || thinking) return;
      setMessages((m) => [...m, { who: "u", text }]);
      setThinking(true);
      let started = false;
      const ensureAssistant = (first: string) => {
        if (!started) {
          started = true;
          setMessages((m) => [...m, { who: "a", text: first }]);
        } else {
          appendToAssistant(first);
        }
      };

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
          const parts = buf.split("\n\n");
          buf = parts.pop() ?? "";
          for (const part of parts) {
            const line = part.trim();
            if (!line.startsWith("data:")) continue;
            const ev = JSON.parse(line.slice(5).trim());
            if (ev.type === "delta") ensureAssistant(ev.text);
            else if (ev.type === "error") {
              if (!started) {
                started = true;
                setMessages((m) => [...m, { who: "a", text: "抱歉，我剛剛沒處理好，可以再說一次嗎？" }]);
              } else {
                replaceAssistant("抱歉，我剛剛沒處理好，可以再說一次嗎？");
              }
            }
          }
        }
      } catch {
        if (!started) setMessages((m) => [...m, { who: "a", text: "抱歉，連線出了點問題，請稍後再試。" }]);
        else replaceAssistant("抱歉，連線出了點問題，請稍後再試。");
      } finally {
        setThinking(false);
      }
    },
    [thinking],
  );

  return { messages, thinking, send };
}
