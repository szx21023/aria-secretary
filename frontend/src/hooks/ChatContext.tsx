import { createContext, useContext, type ReactNode } from "react";

import { useChat } from "./useChat";

// 把 useChat 的單一實例提升到 Context，讓 AIRail 之外的元件（如 EventDetail
// 的「請秘書改期」）也能送訊息進同一條對話，而不會各自開一份 chat 狀態。
type ChatApi = ReturnType<typeof useChat>;

const ChatCtx = createContext<ChatApi | null>(null);

export function ChatProvider({ children }: { children: ReactNode }) {
  const chat = useChat();
  return <ChatCtx.Provider value={chat}>{children}</ChatCtx.Provider>;
}

export function useChatContext(): ChatApi {
  const ctx = useContext(ChatCtx);
  if (!ctx) throw new Error("useChatContext 必須在 <ChatProvider> 內使用");
  return ctx;
}
