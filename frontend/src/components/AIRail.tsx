import { useEffect, useRef, useState } from "react";

import { useChatContext } from "../hooks/ChatContext";
import { COUNTER_SHOW_RATIO, MESSAGE_MAX_LENGTH } from "../lib/chat";
import { Icon } from "../lib/icons";

const CHIPS = ["今天有哪些空檔？", "今天有什麼行程？", "這週的安排", "下午有空嗎？"];

export function AIRail() {
  const { messages, thinking, send } = useChatContext();
  const [val, setVal] = useState("");
  const threadRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = threadRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, thinking]);

  const submit = (text?: string) => {
    const v = (text ?? val).trim();
    if (!v || v.length > MESSAGE_MAX_LENGTH) return;
    send(v);
    setVal("");
  };

  const isNearLimit = val.length >= MESSAGE_MAX_LENGTH * COUNTER_SHOW_RATIO;
  // 不用 input 的 maxLength：貼上長文會被瀏覽器默默截斷，使用者不知道後半段沒送出；
  // 改成照常顯示全文、標出超量並擋住送出，讓使用者自己決定怎麼刪。
  const isOverLimit = val.trim().length > MESSAGE_MAX_LENGTH;

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
        {CHIPS.map((c) => (
          <div key={c} className="s-chip" onClick={() => submit(c)}>
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
        {isNearLimit && (
          <small className={"s-count" + (isOverLimit ? " over" : "")}>
            {val.length}/{MESSAGE_MAX_LENGTH}
          </small>
        )}
        <div
          className={"s-send" + (isOverLimit ? " disabled" : "")}
          title={isOverLimit ? `超過 ${MESSAGE_MAX_LENGTH} 字，請先刪減` : undefined}
          onClick={() => submit()}
        >
          <Icon name="send" strokeWidth={2} />
        </div>
      </div>
    </aside>
  );
}
