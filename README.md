# Aria · 私人秘書

把離線版 HTML prototype 重寫成正規全端應用：**FastAPI 後端 + React/Vite 前端**，
AI 對話層用**真 Claude API（tool use）**讓秘書真的會增刪改行程與待辦。

完整規劃見 [`PLAN.md`](./PLAN.md)。

## 現況

**M5 完成（打磨）** — 後端 FastAPI + SQLAlchemy(async) + SQLite，events/tasks/reminders
完整 CRUD 與排程服務；AI 對話層走真 Claude API（tool use）+ SSE 串流，秘書能讀也能增刪改行程／待辦，
含衝突偵測回報與 `state_changed` 即時刷新前端。對話歷史持久化（DB 落地，reload 不消失，含串流中斷的部分回覆復原），
前端 Vite + React + TS 四視圖 + AIRail 對話側欄 + EventDetail「請秘書改期」+ 主題設定面板
（色彩主題／光暈強度，localStorage 持久化），完整復刻 Aurora 玻璃擬態視覺。

**＋ LINE 串接** — Messaging API webhook 讓你在 LINE 上直接跟秘書對話（與網頁共用同一段記憶），
背景排程器在提醒到點／行程即將開始時主動推播到 LINE。詳見下方「LINE 串接」。
測試：後端 137 passed、前端 12 passed。

里程碑：M0 骨架 ✅ → M1 CRUD ✅ → M2 四視圖 ✅ → M3 AI對話(讀) ✅ → M4 AI對話(寫) ✅ → M5 打磨 ✅ → LINE 串接 ✅
（下一步：M6 可選 — 多使用者 + auth、Docker、部署、週期性提醒重排）

## 跑起來

需求：Python 3.11+（這台用 `python3.12`）、Node 18+。

### 後端（:8000）
```bash
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env          # 之後填 ANTHROPIC_API_KEY（M3 才需要）
.venv/bin/uvicorn app.main:app --reload --port 8000
```
首次啟動會自動建表並 seed（以「今天」為錨點的範例行程/待辦/提醒）。
- 健康檢查：http://localhost:8000/api/health
- API 文件：http://localhost:8000/docs

### 前端（:5173）
```bash
cd frontend
npm install
npm run dev
```
開 http://localhost:5173 。Vite 已把 `/api` proxy 到後端，免設 CORS。

## LINE 串接

在 LINE 上跟秘書對話、提醒/行程到點推播到 LINE。**選用**——不填金鑰就完全不啟用，本機/網頁照常跑。

### 設定
1. 在 [LINE Developers Console](https://developers.line.biz/) 建 Provider → **Messaging API channel**，取得
   **Channel secret** 與 **Channel access token（long-lived）**。
2. 填進 `backend/.env`：
   ```
   LINE_CHANNEL_SECRET=...
   LINE_CHANNEL_ACCESS_TOKEN=...
   # 可選：釘死推播收件人；留空＝自動用最後跟 bot 講話的人
   LINE_PUSH_USER_ID=
   EVENT_REMINDER_LEAD_MIN=10   # 行程提前幾分鐘推
   NOTIFIER_INTERVAL_SEC=60     # 推播掃描間隔；0 = 停用推播但保留對話
   ```
3. 後端要有公開 URL（dev 用 `cloudflared` / `ngrok` 開隧道），把
   **`https://<你的網域>/api/line/webhook`** 設成 channel 的 Webhook URL 並啟用。
4. 用手機加該 channel 為好友，傳一句話即可開始。秘書的推播會送給「最後跟它講話的人」（除非設了 `LINE_PUSH_USER_ID`）。

### 運作
- **對話**：webhook 驗簽 → 立刻回 200 → 背景跑同一套 Claude tool-use agent → 用 reply token 回覆（失敗 fallback push）。
  LINE 與網頁共用同一個全域 conversation，兩邊上下文互通。
- **推播**：背景排程器每 `NOTIFIER_INTERVAL_SEC` 秒掃描，提醒 `trigger_at` 到點、行程在 lead 視窗內即 push，
  靠 `Reminder.fired_at` / `Event.notified_at` 防重複（重啟也不重推）。過期逾 10 分鐘的項目只標記不推，避免復活洗版。
- **已知限制**：週期性提醒（`recurrence`）目前推一次後不自動重排；多人留待 M6。

## 結構
- `backend/app/` — FastAPI（models / schemas / api / ai / line / services）
- `frontend/src/` — React（views / components / hooks / lib / theme）
- `frontend/src/theme/aurora.css` — 從原型抽出的完整設計系統（77 個 `s-*` 樣式）
