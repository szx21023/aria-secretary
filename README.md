# Aria · 私人秘書

把離線版 HTML prototype 重寫成正規全端應用：**FastAPI 後端 + React/Vite 前端**，
AI 對話層用**真 Claude API（tool use）**讓秘書真的會增刪改行程與待辦。

完整規劃見 [`PLAN.md`](./PLAN.md)；部署到 GCP Cloud Run（含 Cloud SQL）見 [`DEPLOY.md`](./DEPLOY.md)。

## 現況

（未完成項目與技術債改由 [Notion 任務清單](https://app.notion.com/p/92b86608ba844e80b738223c497d037d) 統一追蹤）

> ⚠️ **線上已知問題**：Cloud Run 預設開啟 CPU throttling，回應送出後容器 CPU 即被收回，
> 導致 (1) LINE 回覆嚴重延遲（背景 agent 凍住，需下一個請求進來才解凍）、(2) 背景推播排程器停擺。
> 兩者同根因，解法是部署時加 `--no-cpu-throttling`。詳見 [`PLAN.md`](./PLAN.md) 技術債第 10 節。

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

### 命令列直接跟秘書對話（CLI，debug 用）

不用起 server、不用登入，直接在終端機驅動 agent——與網頁／LINE **共用同一顆 agent loop**（`app/ai/agent.py`）、同一組工具。適合測試 agent 與觀察工具呼叫。

```bash
cd backend
.venv/bin/python -m app.ai.cli
```
- 逐字串流回覆，並即時標示 `🔧 呼叫工具：<name>` 與 `✎ 已變更：<resource>`。
- 指令：`/reset` 清空本次對話、`/exit`（或 Ctrl-D）離開。
- 記憶為**獨立臨時**：只活在本行程、結束即丟，**不寫入對話歷史資料表**（與網頁／LINE 的持久化記憶分開）。
- 工具對 events/tasks/reminders 的實際增刪改**仍會寫進 `DATABASE_URL` 指向的資料庫**。要完全隔離、不動到 dev 資料，指一個拋棄式 DB 即可：
  ```bash
  DATABASE_URL="sqlite+aiosqlite:///./scratch.db" .venv/bin/python -m app.ai.cli
  ```

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
   # 對話授權白名單（逗號分隔 userId）；留空＝不限制（見下方安全提醒）
   LINE_ALLOWED_USER_IDS=
   EVENT_REMINDER_LEAD_MIN=10   # 行程提前幾分鐘推
   NOTIFIER_INTERVAL_SEC=60     # 推播掃描間隔；0 = 停用推播但保留對話
   ```
3. 後端要有公開 URL（dev 用 `cloudflared` / `ngrok` 開隧道），把
   **`https://<你的網域>/api/line/webhook`** 設成 channel 的 Webhook URL 並啟用。
4. 用手機加該 channel 為好友，傳一句話即可開始。秘書的推播會送給「最後跟它講話的人」（除非設了 `LINE_PUSH_USER_ID`）。

> **⚠️ 安全提醒**：webhook 簽章只能證明「訊息來自 LINE」，**不能**證明「來自你本人」。
> 若不設 `LINE_ALLOWED_USER_IDS`，任何加到你 bot 的人都能透過秘書讀到你的行程／對話歷史，
> 甚至把推播收件人搶過去。**請務必**先加好友、從後端 log 撈出自己的 `userId`，填進白名單鎖定。
> 未設定時後端啟動會印警告。

### 運作
- **對話**：webhook 驗簽 →（白名單授權檢查）→ 立刻回 200 → 背景跑同一套 Claude tool-use agent →
  用 reply token 回覆（失敗 fallback push）。LINE 與網頁共用同一個全域 conversation，兩邊上下文互通。
- **推播**：背景排程器每 `NOTIFIER_INTERVAL_SEC` 秒掃描，提醒 `trigger_at` 到點、行程在 lead 視窗內即 push，
  靠 `Reminder.fired_at` / `Event.notified_at` 防重複（重啟也不重推）。過期逾 10 分鐘的項目只標記不推，避免復活洗版。
- **已知限制**：週期性提醒（`recurrence`）目前推一次後不自動重排；多人留待 M6。

## 結構
- `backend/app/` — FastAPI（models / schemas / api / ai / line / services）
- `frontend/src/` — React（views / components / hooks / lib / theme）
- `frontend/src/theme/aurora.css` — 從原型抽出的完整設計系統（77 個 `s-*` 樣式）
