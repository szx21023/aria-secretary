# Aria · 私人秘書 — 正規前後端重構計畫

> 把原本的單檔離線 prototype（`秘書系統 - 離線版.html`，omelette bundle）重寫成**正規的全端應用**：
> FastAPI 後端 + React/Vite 前端，AI 對話層改用**真 Claude API（tool use）**讓秘書真的會增刪改行程／待辦。
>
> 規劃日期：2026-06-06　·　情境基準日（原 prototype）：2026-06-05（週五）

---

## 0. 原型盤點（我們要復刻什麼）

原 HTML 是一個純前端、in-memory、寫死資料的 React + Babel 單檔 app，拆解後共 5 個模組：

| 原始模組 | 內容 | 重構去向 |
|---|---|---|
| `data.jsx` | `CAT` 分類、`INITIAL_EVENTS/TASKS/REMINDERS/MESSAGES`、`fmtTime`、`Icon` | → 後端 seed 資料 + 前端 `lib/icons`、`lib/format` |
| `chat.jsx` | `runAI()` 規則式意圖解析（延後/取消/加待辦/找空檔/新增/概覽）＋ `AIRail` 對話側欄 | → **後端 Claude tool use**（取代 runAI）＋ 前端 `AIRail` 元件 |
| `views.jsx` | `TodayView` / `CalendarView` / `TasksView` / `RemindersView` / `EventDetail` | → 前端 4 個 view 元件 + detail modal |
| `app.jsx` | `App` 外框、導覽、狀態提升、AI 串接、Tweaks 主題 | → 前端 `App` + `ThemeProvider` |
| `tweaks-panel.jsx` | omelette 編輯器專用面板（host postMessage 協定） | → **移除**（那是 prototype 工具鏈的東西，正式版用一般設定面板取代或先不做） |

### 0.1 原型的四大視圖（要 1:1 復刻 UI/UX）
1. **今日 (Today)** — 問候 header、行程數/待辦數/空檔 pills、今日時間軸（可點開 detail）、待辦重點、即將提醒。
2. **行事曆 (Calendar)** — 週視圖時間網格（08:00–21:00），事件依分類上色，今日有 now-line。
3. **任務 (Tasks)** — 進行中 / 已完成分組、新增輸入框、優先級標籤（高/中）、完成率。
4. **提醒 (Reminders)** — 提醒清單、kind 圖示（meeting/birthday/bill/health）、開關 toggle。

### 0.2 原型的 AI 行為（`runAI` 涵蓋的意圖）
延後/提前改期（含衝突偵測自動順延）、取消行程、加待辦、找空檔、新增行程/會議、今日概覽、fallback。
→ 正式版用 Claude tool use 覆蓋全部，並可自然語言延伸（多輪、上下文、模糊指令）。

### 0.3 視覺語言（務必保留）
- 暗色玻璃擬態（glassmorphism）+ 極光輝光（aurora glow blobs）。
- `oklch()` 色彩、CSS 變數驅動的主色方案（`--acc1/2/3`）。
- 分類色：會議=紫、專注=青、用餐=黃、個人=綠。
- 字體：Space Grotesk / Sora + Noto Sans TC。
- 細節：進行中(live)行程脈動、now-line、卡片 hover、訊息泡泡、typing 動畫、思考 orb。

---

## 1. 技術棧

### 後端
- **Python 3.11+**、**FastAPI**、**Uvicorn**
- **SQLAlchemy 2.0**（async）+ **SQLite**（dev；保留切 Postgres 的空間）
- **Alembic**（migration）
- **Pydantic v2**（schema / validation）
- **anthropic** SDK（`pip install anthropic`）— Claude API tool use
- **pytest** + httpx（測試）

### 前端
- **React 18 + Vite + TypeScript**
- **TanStack Query**（server state / 快取 / 樂觀更新）
- **React Router**（4 個 view 的路由）
- 原生 CSS / CSS Modules（保留 prototype 的 `oklch` 玻璃擬態，不導入 UI library 以維持原貌）
- 可選：`date-fns`（時間處理）

### AI
- 模型：**`claude-opus-4-8`**
- `thinking: {type: "adaptive"}`、`output_config: {effort: "medium"}`（對話延遲敏感，medium 起步）
- **Tool use**：後端定義工具 → Claude 決定呼叫 → 後端對 DB 執行 → 回傳結果 → Claude 組回覆
- 對話走 **streaming**（SSE）回前端，秘書回覆逐字顯示（復刻 typing 體驗）

---

## 2. 專案結構

```
aria-secretary/
├── PLAN.md                      # ← 本文件
├── README.md
├── docker-compose.yml           # （可選）後端 + 前端一鍵起
│
├── backend/
│   ├── pyproject.toml
│   ├── .env.example             # ANTHROPIC_API_KEY、DATABASE_URL...
│   ├── alembic/
│   ├── app/
│   │   ├── main.py              # FastAPI app、CORS、router 掛載
│   │   ├── config.py            # pydantic-settings
│   │   ├── db.py                # async engine / session
│   │   ├── models/              # SQLAlchemy ORM
│   │   │   ├── event.py
│   │   │   ├── task.py
│   │   │   ├── reminder.py
│   │   │   └── chat.py          # Conversation / Message
│   │   ├── schemas/             # Pydantic（request/response）
│   │   │   ├── event.py  task.py  reminder.py  chat.py
│   │   ├── api/                 # router
│   │   │   ├── events.py        # CRUD
│   │   │   ├── tasks.py         # CRUD + complete
│   │   │   ├── reminders.py     # CRUD + toggle
│   │   │   └── chat.py          # POST /chat (SSE streaming)
│   │   ├── ai/
│   │   │   ├── client.py        # anthropic client 封裝
│   │   │   ├── tools.py         # 工具 JSON schema 定義
│   │   │   ├── executor.py      # tool name → DB 操作
│   │   │   ├── agent.py         # tool-use loop（streaming）
│   │   │   └── system_prompt.py # 秘書人設 system prompt
│   │   ├── services/            # 業務邏輯（find_free_slots、衝突偵測…）
│   │   │   └── scheduling.py
│   │   └── seed.py              # 載入原型的範例資料
│   └── tests/
│
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── index.html
    ├── src/
    │   ├── main.tsx
    │   ├── App.tsx              # 外框、導覽、ThemeProvider
    │   ├── theme/
    │   │   ├── tokens.css       # oklch 色、CSS 變數、glow、字體
    │   │   └── ThemeProvider.tsx
    │   ├── lib/
    │   │   ├── api.ts           # fetch wrapper（指向後端）
    │   │   ├── icons.tsx        # 復刻 Icon（SVG path）
    │   │   ├── format.ts        # fmtTime、日期格式
    │   │   └── types.ts         # Event/Task/Reminder/Message 型別
    │   ├── hooks/
    │   │   ├── useEvents.ts     # TanStack Query
    │   │   ├── useTasks.ts
    │   │   ├── useReminders.ts
    │   │   └── useChat.ts       # SSE streaming 對話
    │   ├── views/
    │   │   ├── TodayView.tsx
    │   │   ├── CalendarView.tsx
    │   │   ├── TasksView.tsx
    │   │   └── RemindersView.tsx
    │   └── components/
    │       ├── Nav.tsx
    │       ├── AIRail.tsx       # 對話側欄
    │       ├── EventDetail.tsx
    │       └── ...（卡片、pill、toggle 等）
    └── tests/
```

---

## 3. 資料模型（DB Schema）

> 原型用 `day(1-7)` + `start(分鐘)` + `dur(分鐘)` 表達時間，這對 prototype 夠用，但正式版改為**真實 datetime**，
> 才能跨日/跨週、做提醒、和真實「現在時間」運作。前端再從 datetime 算回「週幾／第幾分鐘」來畫時間軸。

### 3.1 `events`
| 欄位 | 型別 | 說明 |
|---|---|---|
| id | UUID (PK) | |
| title | str | 標題 |
| start_at | datetime (tz-aware) | 開始時間 |
| end_at | datetime | 結束時間（取代 dur） |
| category | enum: `meeting/focus/meal/personal` | 分類（對應 CAT 色） |
| location | str? | 地點 |
| attendees | int? | 參與人數（原 `people`） |
| status | enum: `scheduled/live/done` | 狀態 |
| note | str? | 秘書備註（如「已由秘書順延 1 小時」） |
| created_at / updated_at | datetime | |

### 3.2 `tasks`
| 欄位 | 型別 | 說明 |
|---|---|---|
| id | UUID | |
| title | str | |
| due_at | datetime? | 到期（原 `due` 是字串「今天 17:00」→ 存 datetime，前端格式化顯示） |
| priority | enum: `high/medium/low` ? | 原 `prio: hi/md/null` |
| done | bool | |
| created_at / updated_at | | |

### 3.3 `reminders`
| 欄位 | 型別 | 說明 |
|---|---|---|
| id | UUID | |
| title | str | |
| subtitle | str? | 原 `sub` |
| trigger_at | datetime? | 原 `when`（「15 分鐘後」「每天 08:00」→ 存時間/規則） |
| recurrence | str? | 重複規則（每天/每週…），可後期再做 |
| kind | enum: `meeting/birthday/bill/health` | 圖示與色 |
| enabled | bool | 原 `on` |

### 3.4 `conversations` / `messages`（對話持久化）
- `conversations`: id, title?, created_at
- `messages`: id, conversation_id (FK), role (`user`/`assistant`/`system`/`tool`), content (text), tool_calls (JSON?), created_at

> MVP 可先單一 conversation（單使用者），之後再擴充多會話 / 多使用者（加 `users` 表 + auth）。

### 3.5 Seed 資料
把原型 `INITIAL_EVENTS/TASKS/REMINDERS/MESSAGES` 轉成以「基準日」為錨點的 datetime 寫入 `seed.py`，
讓重構版開箱即有跟原型一樣的畫面。

---

## 4. 後端 REST API

> 一律 `/api` prefix，回傳 Pydantic schema。CRUD 走標準 REST；對話另開 streaming endpoint。

### 4.1 Events
- `GET    /api/events?from=&to=` — 區間查詢（給週視圖/今日）
- `POST   /api/events`
- `GET    /api/events/{id}`
- `PATCH  /api/events/{id}` — 改期/改狀態（含衝突偵測，見 §6）
- `DELETE /api/events/{id}`

### 4.2 Tasks
- `GET /api/tasks`、`POST /api/tasks`、`PATCH /api/tasks/{id}`（含 toggle done）、`DELETE /api/tasks/{id}`

### 4.3 Reminders
- `GET /api/reminders`、`POST`、`PATCH /api/reminders/{id}`（含 toggle enabled）、`DELETE`

### 4.4 Chat（AI 秘書）
- `POST /api/chat` — body: `{ message, conversation_id? }`
  - 回傳 **SSE 串流**：`token`（逐字回覆）、`tool_call`（秘書正在做什麼，給前端顯示「正在處理…」）、
    `state_changed`（哪些資源被改了 → 前端 invalidate query 重抓）、`done`。
- `GET /api/chat/history?conversation_id=` — 載入歷史訊息

---

## 5. AI 層設計（核心：取代 runAI）

### 5.1 流程
```
使用者輸入 → POST /api/chat
  → 載入對話歷史 + system prompt + 工具定義
  → client.messages.stream(model=claude-opus-4-8, thinking=adaptive, tools=[...])
  → while stop_reason == "tool_use":
        執行工具（executor 對 DB 操作）→ 回 tool_result → 續跑
  → 串流秘書回覆文字回前端
  → 持久化訊息、發 state_changed 事件
```
採**手動 agentic loop**（非 tool_runner），因為要：串流逐字、攔截每個 tool call 推 SSE、控制權限。

### 5.2 工具集（`ai/tools.py`，對應原 runAI 的意圖）
| 工具 | 參數 | 對應原行為 |
|---|---|---|
| `get_schedule` | `date?`（預設今天） | 今日概覽、查行程 |
| `create_event` | title, start_at, duration_min, category?, location?, attendees? | 安排/新增會議 |
| `reschedule_event` | event_id 或 query(關鍵字), delta_min 或 new_start_at | 延後/提前/改到（含衝突自動順延） |
| `cancel_event` | event_id 或 query | 取消/刪除 |
| `add_task` | title, due_at?, priority? | 提醒我/加待辦 |
| `complete_task` | task_id 或 query | 完成待辦 |
| `find_free_slots` | date?, min_minutes? | 找空檔 |
| `create_reminder` / `toggle_reminder` | … | 提醒管理 |

> 工具 `description` 要寫清楚**何時呼叫**（Opus 4.8 對「何時用」很敏感，能提高正確觸發率）。
> 模糊指令（「把下午的簡報延後一小時」）由 Claude 自己從 `get_schedule` 找到目標 event_id，再呼叫 `reschedule_event`。

### 5.3 System Prompt（秘書人設）
- 角色：「Aria，使用者的私人秘書」，繁體中文、簡潔、主動、禮貌。
- 注入**動態情境**（現在時間、使用者名）走 message 層而非寫死 system（保 prompt cache）。
- 行為準則：改完行程要確認、偵測衝突要主動講、不確定就問。

### 5.4 衝突偵測
`reschedule_event` / `create_event` 後呼叫 `services/scheduling.detect_conflicts()`，
若重疊則自動把被擋的行程順延（復刻原型 `pushed` 邏輯），並在回覆中說明。

---

## 6. 前端設計

### 6.1 狀態管理
- Server state（events/tasks/reminders/messages）→ **TanStack Query**，CRUD 後 invalidate 重抓。
- 對話 streaming → `useChat` hook 接 SSE，`state_changed` 事件觸發對應 query invalidate（秘書改完，畫面即時更新）。
- 主題（色方案/glow/字體）→ `ThemeProvider` + CSS 變數（保留原 Tweaks 概念，但用一般設定面板）。

### 6.2 元件對應
- `App` → 導覽 + 路由 + AIRail 常駐 + ThemeProvider。
- 4 個 view 從 `views.jsx` 1:1 移植，資料來源換成 hook。
- `AIRail` 從 `chat.jsx` 移植：訊息泡泡、chips 快捷、輸入列、思考 orb、typing 動畫；送出改打 `/api/chat` SSE。
- `EventDetail` modal：「請秘書改期」按鈕 → 送一句自然語言進對話（同原型）。

### 6.3 視覺移植
把原 HTML `<style>`（玻璃擬態、glow、oklch、動畫）整理進 `theme/tokens.css` 與各元件 CSS Module，
類名沿用 `s-*` 以利對照，確保**像素級復刻**原型外觀。

---

## 7. 開發順序（里程碑）

> 偏好：新專案一次全展開規劃，實作分階段。每階段結束都能 demo。

1. **M0 — 骨架**：建 backend（FastAPI hello + DB + models + alembic）、frontend（Vite + 空殼 + theme tokens）。
2. **M1 — CRUD 後端**：events/tasks/reminders 三組 REST + seed + pytest。
3. **M2 — 前端四視圖**：移植 4 個 view + Nav + theme，接真 API（先不做 AI）。畫面與原型一致。
4. **M3 — AI 對話（讀）**：`/api/chat` streaming + system prompt + `get_schedule`/`find_free_slots`（唯讀工具）+ AIRail。
5. **M4 — AI 對話（寫）**：加 create/reschedule/cancel/add_task/toggle 工具 + 衝突偵測 + `state_changed` 即時刷新。
6. **M5 — 打磨** ✅：對話歷史持久化（DB 落地 + `GET /api/chat/history`，含串流中斷的部分回覆復原）、錯誤處理（後端串流 try/except + 復原存檔；前端 retry/連線失敗訊息）、loading/empty state、EventDetail「請秘書改期」接上對話、設定面板（色彩主題 + 光暈強度，localStorage 持久化 + vitest）。
7. **M6（可選）**：多使用者 + auth、Docker、部署、提醒實際觸發（背景排程）、多對話 thread（目前為單一全域 conversation）。

> 行事曆三視圖（日／週／月）已於後續補上（`views/calendar/` 的 `TimeGrid`＝日/週共用、`MonthGrid`＝月）。

### 行事曆已知待修（PR review 後盤點，刻意未塞進三視圖 PR）
- [x] **跨午夜／跨日行程渲染** — 已修：`lib/format` 新增 `daySegment()`（事件在某日 00:00–24:00 的可見區段），`TimeGrid` 改用它過濾＋clamp 高度、`MonthGrid` 改用它過濾，跨日行程每個重疊日各畫一段。
- [x] **`now` 不會 tick** — 已修：`CalendarView` 的 `now` 改為 state＋每分鐘 `setInterval` 更新（unmount 時清除）。
- [x] **跨夜行程延續段的時間標籤** — 已修：延續段（事件不是該天開始的）標籤顯示「← 23:00」，箭頭表示從前一天延續而來。

---

## 8. 環境變數 / 設定
```
# backend/.env
ANTHROPIC_API_KEY=sk-ant-...
DATABASE_URL=sqlite+aiosqlite:///./aria.db
CORS_ORIGINS=http://localhost:5173
APP_TZ=Asia/Taipei
```
```
# frontend/.env
VITE_API_BASE=http://localhost:8000
```

---

## 9. 待你確認 / 決策點（實作前可再對齊）
- [x] 是否要**多使用者 + 登入** → MVP 先單人本機（未加 users/auth）。多使用者留 M6。
- [x] 提醒（reminders）是否要**真的會在時間到時觸發通知** → MVP 先只做清單管理；實際觸發留 M6。
- [x] 「現在時間」 → 用**真實系統時間** + seed 以「今天」為錨。
- [x] 主題設定面板要不要做（原 Tweaks）→ M5 已做（色彩主題 + 光暈強度，localStorage 持久化）。

> 下一步：你確認本計畫後，我從 **M0 骨架**開始建。
