// 單則訊息長度上限（字元）。必須與後端 backend/app/schemas/chat.py 的 MESSAGE_MAX_LENGTH 一致：
// 前端擋是為了即時提示，真正把關在後端；兩邊不一致時後端回 422，由 tooLongReply 顯示正確原因。
export const MESSAGE_MAX_LENGTH = 4000;

// 字數提示在用到上限的這個比例後才出現，平常不佔版面
export const COUNTER_SHOW_RATIO = 0.8;

// 後端 422 的錯誤內容（exception_handlers 的統一格式）；只描述判斷「訊息太長」需要的欄位
interface ValidationErrorBody {
  error?: { details?: { errors?: { type?: string; ctx?: { max_length?: number } }[] } };
}

/** 後端回 422 時，若原因是訊息太長就回給使用者看的說明，否則回 null。上限以後端回報的為準。 */
export function tooLongReply(body: unknown): string | null {
  const errors = (body as ValidationErrorBody | null)?.error?.details?.errors ?? [];
  const tooLong = errors.find((e) => e.type === "string_too_long");
  if (!tooLong) return null;
  const limit = tooLong.ctx?.max_length ?? MESSAGE_MAX_LENGTH;
  return `訊息太長了（上限 ${limit} 字），請縮短或分段傳送。`;
}
