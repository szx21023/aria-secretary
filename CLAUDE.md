# CLAUDE.md

本檔案為 **Aria · 私人秘書** 專案的開發規範，Claude 每次協作時皆會自動載入並遵循。

> 本檔由通用範本（`claude_instruction`）客製而來，以本檔記錄的專案實況為準。

## 專案概述

- **全端私人秘書**：FastAPI 後端 + React/Vite 前端；AI 對話層走**真 Claude API（tool use）+ SSE 串流**，秘書能讀也能增刪改行程／待辦（events / tasks / reminders）。
- 資料層：SQLAlchemy 2.0（async）；本機 SQLite、線上 Cloud SQL(Postgres)；migration 用 Alembic。
- **LINE 串接**（選用）：Messaging API webhook 讓你在 LINE 上跟秘書對話（與網頁共用同一段記憶），背景排程器在提醒／行程到點時主動推播。
- 部署：前後端 Dockerfile + `deploy.sh` 一鍵上 Cloud Run；細節見 [`DEPLOY.md`](./DEPLOY.md)，完整規劃見 [`PLAN.md`](./PLAN.md)。
- 現況：M5 完成 + LINE 串接 + M6 部分（auth／Docker／Cloud Run／Cloud SQL）；未完項目改由 Notion 任務清單追蹤。

## 常用指令

### 後端（`backend/`，:8000）
- 建虛擬環境 + 安裝：`python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"`
- 首次啟用 pre-commit：`.venv/bin/pre-commit install`
- 啟動開發伺服器：`.venv/bin/uvicorn app.main:app --reload --port 8000`（首次啟動自動建表並 seed）
- 跑測試：`.venv/bin/pytest`
- lint + 格式檢查：`ruff check . && ruff format --check .`
- 自動修正：`ruff check --fix . && ruff format .`
- 手動對所有檔案跑 pre-commit：`pre-commit run --all-files`
- 健康檢查 http://localhost:8000/api/health ／ API 文件 http://localhost:8000/docs

### 前端（`frontend/`，:5173）
- 安裝：`npm install`
- 開發：`npm run dev`（Vite 已把 `/api` proxy 到後端，免設 CORS）
- 建置：`npm run build`（`tsc -b && vite build`）
- 測試：`npm run test`（vitest）
- lint／格式：`npm run lint`、`npm run format`、`npm run typecheck`

## 專案架構

後端採**分層式（layer-based）**組織：先按技術層切目錄，同一資源（event / task / reminder…）的檔案分散在各層以同名檔對應。

### 後端目錄結構
```
backend/app/
├── main.py               # FastAPI 進入點：建立 app、掛 router、註冊 exception handler、lifespan（含 LINE notifier 排程）
├── config.py             # pydantic-settings 設定（get_settings 單例）
├── db.py                 # async engine / session、Base
├── exception_handlers.py # 自訂例外 → 統一 HTTP 回應
├── seed.py               # 首次啟動的範例資料
├── api/                  # 路由層：一資源一檔（events.py / tasks.py / reminders.py / chat.py / auth.py / line.py …）
├── services/             # 商業邏輯層
├── schemas/              # Pydantic 輸入／輸出（一資源一檔）
├── models/               # SQLAlchemy ORM 模型
├── ai/                   # Claude API tool-use agent（對話、工具、串流）
├── line/                 # LINE webhook 驗簽、回覆、推播排程
└── common/               # 跨層共用工具

backend/tests/            # pytest（asyncio_mode=auto）
backend/alembic/          # migration
```

### 前端目錄結構
```
frontend/src/
├── views/        # 四大視圖（含 calendar/）
├── components/   # UI 元件（含 AIRail 對話側欄、EventDetail…）
├── hooks/        # React hooks
├── lib/          # API client 等
└── theme/        # aurora.css — 從原型抽出的完整設計系統（s-* 樣式）
```

### 架構規則
- **依賴方向單向**：`api → services → models`，不可反向（service 不 import api 層 router）
- **schema 與 model 分離**：對外一律回 `schemas/` 的 Pydantic 型別，不直接吐 ORM 物件
- **同資源跨層以同名檔對應**：`api/events.py` ↔ `services/…` ↔ `schemas/event.py` ↔ `models/…`，新增資源時比照建立
- **router 保持薄**：不在 router 寫商業邏輯，也不在 router 直接建立 DB session / client
- **AI／LINE 共用同一套 agent**：網頁與 LINE 對話走同一個 `ai/` agent 與同一段全域對話記憶，改動時兩邊都要顧到

## 程式風格

### 語言與工具鏈
- Python 3.11+（本機用 `python3.12`）；所有函式簽名必須有 type hints；避免裸露的 `Any`，但無法用 union 增加安全性的異質 payload 可用 `Any`
- 格式化與 lint 統一用 `ruff`（`ruff format` + `ruff check`），提交前必須零錯誤；規則見 `backend/pyproject.toml` 的 `[tool.ruff]`（**line-length = 120**，放寬給中文註解／字串）
- 安全掃描用 `bandit`（設定見 `[tool.bandit]`）
- lint/格式在 `git commit` 時由 pre-commit 自動執行並擋關；首次需 `pre-commit install`
- import 排序交給 ruff，不要手動調整；不使用相對 import，一律絕對 import
- 資料在層與層之間一律用 Pydantic v2 / ORM 型別傳遞，不要用裸 dict

### 命名慣例
- 變數/函式：snake_case；類別：PascalCase；常數：UPPER_SNAKE
- 變數名稱用完整單字，不要用縮寫或單一字元（用 `ticket` 不要用 `t`）；慣用的 loop 計數短名視情況可接受
- 布林值用 is_/has_/should_ 開頭（如 is_active）
- **Pydantic schema 命名**：類別一律以 `Schema` 結尾。語意後綴仍保留——輸入用 `Xxx(Create|Update)Schema`（如 `EventCreateSchema` / `TaskUpdateSchema`）、對外輸出用 `XxxReadSchema`（如 `EventReadSchema`）、請求體用 `XxxRequestSchema`。
  > 註：SSE 事件協定的 `TypedDict`（`DeltaEvent` / `DoneEvent` 等）不屬 DTO schema，維持 `*Event` 命名、不加 `Schema`。
- 私有成員以單底線開頭 `_internal`
- 常數依使用 scope 放置：只在單一模組用就放該模組（`constants.py` 或檔案頂部），跨層才上提到共用層；環境可調的值進 `config.py`（Settings）。常數集中檔一律命名 `constants.py`
- **列舉**：ruff 豁免 `UP042`，本專案**保留** `class X(str, Enum)` 寫法（改 `StrEnum` 對 SQLAlchemy/Pydantic 序列化行為有變動風險），沿用即可

### FastAPI 慣例
- 路由函式只做「參數驗證 → 呼叫 service → 回傳」，商業邏輯一律放 service 層
- 依賴注入用 `Depends`，不要在函式內自行建立 DB session / client
- 所有 I/O（DB、Claude API、LINE、外部 API）一律用 async；不要在 async 路由裡呼叫同步阻塞函式
- 回傳資料的端點明確指定 response_model；健康檢查／狀態探針類端點回固定結構的裸 dict 可接受
- 路徑用複數名詞（`/events`、`/tasks/{id}`），不要動詞化路徑
- SSE 串流端點維持既有事件型別契約（`DeltaEvent` / `ToolEvent` / `StateChangedEvent` / `DoneEvent` / `ErrorEvent`），前端 AIRail 依賴這些型別刷新

### 錯誤處理
- 業務錯誤拋自訂 exception，由 `exception_handlers.py` 的統一 handler 轉成 HTTP 回應
- 不要在 router 直接 raise `HTTPException` 散落各處；不要吞例外（禁止空的 except）
- **禁止 print**；一律用 `logging`，並帶上 request 相關 context（目前程式碼已全面遵守）

### 結構與複雜度
- 函式超過 50 行或巢狀超過 3 層就拆分
- 優先 early return，避免深層 else 巢狀
- 設定值只從 `config`（pydantic-settings）讀取，禁止散落的 `os.getenv`

### 前端慣例（React / TS）
- TypeScript 嚴格模式；提交前 `npm run typecheck` 零錯誤
- lint 用 eslint（含 react-hooks 規則）、格式用 prettier；不手動排版
- 元件放 `components/`、頁面放 `views/`、資料存取邏輯抽到 `hooks/` 或 `lib/`，不要在元件裡直接寫 fetch
- 樣式沿用 `theme/aurora.css` 的 `s-*` 設計系統，不要另立一套視覺
- 測試用 vitest；改到 API 契約時前後端測試都要跟上

### 註解
- 註解寫「為什麼」，不寫「做什麼」
- 公開函式與 service 方法用 docstring 說明參數、回傳、可能拋的例外
- 不要為顯而易見的程式碼加註解
