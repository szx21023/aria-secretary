# 部署到 GCP Cloud Run

backend 與 frontend 各部署成一個 Cloud Run 服務。

## 一次性設定

```bash
cp deploy.env.example deploy.env   # 填入 GCP_PROJECT、GCP_ACCOUNT
```

需求:
- 已安裝 `gcloud`,且該帳號已登入(`gcloud auth login <帳號>`)
- 目標 GCP 專案**已開通計費(billing)**
- `backend/.env` 內有:
  - `ANTHROPIC_API_KEY`
  - `APP_PASSWORD` —— 網頁登入密碼(你自己選,**不可含 `@`**)
  - `AUTH_SECRET` —— JWT 簽章密鑰,建議 ≥32 bytes 隨機值:
    `python -c 'import secrets; print(secrets.token_hex(32))'`

## 部署

```bash
./deploy.sh
```

腳本會依序:
1. 開通 `run` / `cloudbuild` / `artifactregistry` API
2. 用 `backend/Dockerfile` build 並部署 **aria-backend**(uvicorn 監聽 `$PORT`)
3. 把 backend 網址寫進 `frontend/.env.production`(`VITE_API_BASE`)
4. 用 `frontend/Dockerfile`(node build → nginx)build 並部署 **aria-frontend**
5. 把 backend 的 `CORS_ORIGINS` 收斂成 frontend 網址

完成後印出兩個服務的 URL。重複執行會滾動更新。

## 架構與檔案

| 檔案 | 作用 |
|------|------|
| `backend/Dockerfile` | python:3.11-slim + `pip install .` + uvicorn |
| `backend/.gcloudignore` | 排除 `.env`、`*.db`、快取不上傳 |
| `frontend/Dockerfile` | 多階段:node build → nginx 服務 `dist` |
| `frontend/nginx.conf` | 監聽 8080、SPA fallback 回 `index.html` |
| `frontend/.env.production` | `VITE_API_BASE`(由腳本自動覆寫) |

## 注意事項

- **資料持久化(Cloud SQL)**:不設定時 backend 用容器 `/tmp` 的 SQLite,重啟/擴縮即重置、多實例不共用(僅適合 demo)。
  正式環境接 **Cloud SQL (Postgres)**:
  1. `deploy.env` 設 `CLOUDSQL_INSTANCE=PROJECT:REGION:INSTANCE`(deploy.sh 會 `--add-cloudsql-instances` 掛上)。
  2. `backend/.env` 的 `DATABASE_URL` 改成 unix socket 形式:
     `postgresql+asyncpg://USER:PASS@/DBNAME?host=/cloudsql/PROJECT:REGION:INSTANCE`。<!-- pragma: allowlist secret -->
  3. 後端相依已含 `asyncpg`(app)與 `psycopg2-binary`(Alembic migration);啟動時 `init_db()` 自動 `alembic upgrade head`。
  最便宜配置:`db-f1-micro` + 10GB HDD + 無備份 + 單一 zone,約 US$9–10/月(實例 24h 常開,不會縮到零)。
- **金鑰**:`ANTHROPIC_API_KEY` 目前以環境變數注入。要更安全可改用 **Secret Manager**
  (`gcloud run deploy ... --set-secrets ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest`)。
- 兩個服務皆 `--allow-unauthenticated`(Cloud Run 層公開)。**存取控制在應用層**:
  backend 的 `/api/*`(events/tasks/reminders/chat)需登入(Bearer JWT),前端有登入頁;
  `/api/health` 與 `/api/auth/login` 公開;LINE webhook 走自己的簽章+白名單。
  注意 CORS **不是**存取控制(擋不住 curl/腳本),真正的把關是 JWT。
