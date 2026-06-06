# Aria · 私人秘書

把離線版 HTML prototype 重寫成正規全端應用：**FastAPI 後端 + React/Vite 前端**，
AI 對話層用**真 Claude API（tool use）**讓秘書真的會增刪改行程與待辦。

完整規劃見 [`PLAN.md`](./PLAN.md)。

## 現況

**M0 骨架完成** — 後端 FastAPI + SQLAlchemy(async) + SQLite 跑起來、seed 範例資料、唯讀 API；
前端 Vite + React + TS 外殼，完整復刻 Aurora 玻璃擬態視覺，已串接後端。

里程碑：M0 骨架 ✅ → M1 CRUD → M2 四視圖 → M3 AI對話(讀) → M4 AI對話(寫) → M5 打磨

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

## 結構
- `backend/app/` — FastAPI（models / schemas / api / ai / services）
- `frontend/src/` — React（views / components / hooks / lib / theme）
- `frontend/src/theme/aurora.css` — 從原型抽出的完整設計系統（77 個 `s-*` 樣式）
