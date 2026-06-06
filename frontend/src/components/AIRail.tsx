import { useEffect, useRef, useState } from "react";

import { useChat } from "../hooks/useChat";
import { Icon } from "../lib/icons";

const CHIPS = ["今天有哪些空檔？", "今天有什麼行程？", "這週的安排", "下午有空嗎？"];

export function AIRail() {
  const { messages, thinking, send } = useChat();
  const [val, setVal] = useState("");
  const threadRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = threadRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, thinking]);

  const submit = (text?: string) => {
    const v = (text ?? val).trim();
    if (!v) return;
    send(v);
    setVal("");
  };

  return (
    <aside className="s-rail">
      <div className="s-rail-h">
        <div className={"s-orb" + (thinking ? " think" : "")} />
        <b>秘書 Aria</b>
        <small>{thinking ? "正在處理…" : "隨時為你安排"}</small>
      </div>

      <div className="s-thread" ref={threadRef}>
        {messages.map((m, i) => (
          <div key={i} className={"s-bub " + m.who}>
            {m.text}
          </div>
        ))}
        {thinking && (
          <div className="s-typing">
            <i />
            <i />
            <i />
          </div>
        )}
      </div>

      <div className="s-chips">
        {CHIPS.map((c, i) => (
          <div key={i} className="s-chip" onClick={() => submit(c)}>
            {c}
          </div>
        ))}
      </div>

      <div className="s-inputbar">
        <span className="s-mic">
          <Icon name="mic" />
        </span>
        <input
          value={val}
          placeholder="輸入或說出你的需求…"
          onChange={(e) => setVal(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
          }}
        />
        <div className="s-send" onClick={() => submit()}>
          <Icon name="send" strokeWidth={2} />
        </div>
      </div>
    </aside>
  );
}
