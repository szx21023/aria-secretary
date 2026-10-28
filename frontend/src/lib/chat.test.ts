import { describe, expect, it } from "vitest";

import { MESSAGE_MAX_LENGTH, tooLongReply } from "./chat";

// 後端 /api/chat 對超長訊息實際回的 422 內容（節錄）
const tooLongBody = (maxLength?: number) => ({
  error: {
    code: "validation_error",
    details: {
      errors: [
        {
          type: "string_too_long",
          loc: ["body", "message"],
          ctx: maxLength ? { max_length: maxLength } : {},
        },
      ],
    },
  },
});

describe("tooLongReply", () => {
  it("訊息太長 → 用後端回報的上限組說明", () => {
    expect(tooLongReply(tooLongBody(10))).toBe("訊息太長了（上限 10 字），請縮短或分段傳送。");
  });

  it("後端沒給上限 → 退回前端常數", () => {
    expect(tooLongReply(tooLongBody())).toContain(`上限 ${MESSAGE_MAX_LENGTH} 字`);
  });

  it("其他驗證錯誤或非預期格式 → null，交給一般錯誤處理", () => {
    expect(tooLongReply({ error: { details: { errors: [{ type: "missing" }] } } })).toBeNull();
    expect(tooLongReply({ detail: "x" })).toBeNull();
    expect(tooLongReply(null)).toBeNull();
  });
});
