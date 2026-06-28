#!/usr/bin/env bash
#
# 把 aria-secretary 的 backend + frontend 部署到 GCP Cloud Run。
# 可重複執行（idempotent）：每次跑都會 build 新映像並滾動更新。
#
# 用法：
#   1. cp deploy.env.example deploy.env  並填入你的 GCP 專案 / 帳號
#   2. 確認 backend/.env 內有 ANTHROPIC_API_KEY
#   3. ./deploy.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 設定來源：deploy.env（gitignore）優先，其次環境變數
[ -f "$SCRIPT_DIR/deploy.env" ] && source "$SCRIPT_DIR/deploy.env"

PROJECT="${GCP_PROJECT:?請在 deploy.env 設定 GCP_PROJECT}"
ACCOUNT="${GCP_ACCOUNT:?請在 deploy.env 設定 GCP_ACCOUNT}"
REGION="${GCP_REGION:-asia-east1}"
BACKEND_SERVICE="${BACKEND_SERVICE:-aria-backend}"
FRONTEND_SERVICE="${FRONTEND_SERVICE:-aria-frontend}"
# 接 Cloud SQL 時填連線名稱（PROJECT:REGION:INSTANCE）；留空＝沿用容器內 SQLite。
CLOUDSQL_INSTANCE="${CLOUDSQL_INSTANCE:-}"

GC=(gcloud --project="$PROJECT" --account="$ACCOUNT")

echo "==> [1/5] 開通必要 API"
"${GC[@]}" services enable \
  run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

echo "==> [2/5] 部署 backend（CORS 先放寬，稍後收斂）"
# 注意：KEY=$(...) 這種賦值即使命令替換失敗，set -e 也不會中止，故需顯式檢查。
ENV_FILE="$SCRIPT_DIR/backend/.env"
[ -f "$ENV_FILE" ] || { echo "ERROR: 找不到 $ENV_FILE，無法取得 ANTHROPIC_API_KEY" >&2; exit 1; }
KEY=$(grep -E '^ANTHROPIC_API_KEY=' "$ENV_FILE" | head -n1 | cut -d= -f2- | tr -d "\"'")
[ -n "$KEY" ] || { echo "ERROR: $ENV_FILE 內沒有非空的 ANTHROPIC_API_KEY" >&2; exit 1; }

# 網頁登入：密碼 + JWT 簽章密鑰。兩者缺一就 fail closed（API 全 401＝鎖死無法用），
# 故部署前就強制要求，避免推出一個自己也登不進去的服務。
APP_PASSWORD=$(grep -E '^APP_PASSWORD=' "$ENV_FILE" | head -n1 | cut -d= -f2- | tr -d "\"'")
[ -n "$APP_PASSWORD" ] || { echo "ERROR: $ENV_FILE 內沒有 APP_PASSWORD（網頁登入密碼）" >&2; exit 1; }
AUTH_SECRET=$(grep -E '^AUTH_SECRET=' "$ENV_FILE" | head -n1 | cut -d= -f2- | tr -d "\"'")
[ -n "$AUTH_SECRET" ] || { echo "ERROR: $ENV_FILE 內沒有 AUTH_SECRET（JWT 簽章密鑰）" >&2; exit 1; }
# 密碼限 ASCII 可見字元（中文/emoji 後端比對會出錯、前端也擋輸入）。
if printf '%s' "$APP_PASSWORD" | LC_ALL=C grep -q '[^ -~]'; then
  echo "ERROR: APP_PASSWORD 只能用 ASCII 可見字元（不可含中文/emoji/控制字元）" >&2; exit 1
fi
# 值會以 ^|^ 分隔注入；密碼含 '|' 會破壞分隔，寧可明確擋下也不要悄悄注入錯誤的值。
case "$APP_PASSWORD" in *\|*) echo "ERROR: APP_PASSWORD 不可含 '|'（與部署分隔符衝突），請改一個不含 | 的密碼" >&2; exit 1;; esac

# 資料庫連線字串：優先取 backend/.env 的 DATABASE_URL（接 Cloud SQL Postgres 時在此設定，
# 形如 postgresql+asyncpg://USER:PASS@/DB?host=/cloudsql/PROJECT:REGION:INSTANCE）；  # pragma: allowlist secret
# 未設定則退回容器內 SQLite（/tmp，重啟即失，僅適合 demo）。
DB_URL=$(grep -E '^DATABASE_URL=' "$ENV_FILE" | head -n1 | cut -d= -f2- | tr -d "\"'")
DB_URL="${DB_URL:-sqlite+aiosqlite:////tmp/aria.db}"

# 接 Cloud SQL 時做一致性檢查：CLOUDSQL_INSTANCE 與 DATABASE_URL 各自設定，任一缺漏都會
# 悄悄退回 /tmp SQLite（資料每次冷啟動即失），banner 卻一切正常——這裡明確擋下、fail closed。
if [ -n "$CLOUDSQL_INSTANCE" ]; then
  case "$DB_URL" in
    postgresql*) ;;
    *) echo "ERROR: 已設 CLOUDSQL_INSTANCE，但 $ENV_FILE 的 DATABASE_URL 不是 Postgres（取得：${DB_URL:-空}）；Cloud SQL 會被掛上卻永遠用不到，app 仍寫入容器內 SQLite" >&2; exit 1;;
  esac
  case "$DB_URL" in
    *"$CLOUDSQL_INSTANCE"*) ;;
    *) echo "ERROR: DATABASE_URL 的 host=/cloudsql/... 連線名稱與 CLOUDSQL_INSTANCE（$CLOUDSQL_INSTANCE）不一致" >&2; exit 1;;
  esac
else
  # 反向守門：DATABASE_URL 已是 Postgres 卻沒設 CLOUDSQL_INSTANCE，則 --add-cloudsql-instances
  # 不會掛、/cloudsql/<連線名稱> socket 不存在，啟動時 init_db() 連線即失敗（崩潰但訊息晦澀）。
  # 部署前明確擋下，給出可讀的中文錯誤而非 libpq 的 socket 天書。
  case "$DB_URL" in
    postgresql*) echo "ERROR: DATABASE_URL 是 Postgres 但未設 CLOUDSQL_INSTANCE；Cloud Run 不會掛 /cloudsql socket，啟動即連線失敗。請在 deploy.env 設 CLOUDSQL_INSTANCE=PROJECT:REGION:INSTANCE" >&2; exit 1;;
  esac
fi

# DB_URL 是 operator 提供的值（Postgres 密碼可能含任意字元）；含 '|' 會破壞下面的 ^|^ 分隔。
case "$DB_URL" in *\|*) echo "ERROR: DATABASE_URL 不可含 '|'（與部署分隔符衝突）" >&2; exit 1;; esac

# 用 ^|^ 自訂分隔符：值含 @（Postgres URL）、+/=（LINE token）等特殊字元，pipe 不會出現在任何值中
# （APP_PASSWORD 與 DATABASE_URL 已於上方明確擋下含 '|' 的情形）。
ENV_VARS="^|^DATABASE_URL=${DB_URL}|APP_TZ=Asia/Taipei|CORS_ORIGINS=*|SEED_ON_EMPTY=false|ANTHROPIC_API_KEY=${KEY}|APP_PASSWORD=${APP_PASSWORD}|AUTH_SECRET=${AUTH_SECRET}"

# 選填：LINE（secret 與 token 都備齊才注入；缺任一就維持純網頁模式）
LINE_SECRET=$(grep -E '^LINE_CHANNEL_SECRET=' "$ENV_FILE" | head -n1 | cut -d= -f2-)
LINE_TOKEN=$(grep -E '^LINE_CHANNEL_ACCESS_TOKEN=' "$ENV_FILE" | head -n1 | cut -d= -f2-)
if [ -n "$LINE_SECRET" ] && [ -n "$LINE_TOKEN" ]; then
  ENV_VARS="${ENV_VARS}|LINE_CHANNEL_SECRET=${LINE_SECRET}|LINE_CHANNEL_ACCESS_TOKEN=${LINE_TOKEN}"
  # 白名單與推播目標也要一起帶，否則部署的服務永遠是「不限制」全開狀態，
  # README 要求的鎖定會被部署路徑悄悄繞過（安全洞）。空值代表不設定（維持全開）。
  LINE_ALLOWED=$(grep -E '^LINE_ALLOWED_USER_IDS=' "$ENV_FILE" | head -n1 | cut -d= -f2-)
  LINE_PUSH_ID=$(grep -E '^LINE_PUSH_USER_ID=' "$ENV_FILE" | head -n1 | cut -d= -f2-)
  [ -n "$LINE_ALLOWED" ] && ENV_VARS="${ENV_VARS}|LINE_ALLOWED_USER_IDS=${LINE_ALLOWED}"
  [ -n "$LINE_PUSH_ID" ] && ENV_VARS="${ENV_VARS}|LINE_PUSH_USER_ID=${LINE_PUSH_ID}"
  if [ -n "$LINE_ALLOWED" ]; then
    echo "    （偵測到 LINE 設定，一併注入；白名單已啟用）"
  else
    echo "    （偵測到 LINE 設定，一併注入；⚠️ 未設白名單＝任何人都能對話）"
  fi
fi

# 接 Cloud SQL：掛上實例，Cloud Run 會在 /cloudsql/<連線名稱> 放 unix socket 供 backend 連線。
CLOUDSQL_ARGS=()
[ -n "$CLOUDSQL_INSTANCE" ] && CLOUDSQL_ARGS=(--add-cloudsql-instances "$CLOUDSQL_INSTANCE")

"${GC[@]}" run deploy "$BACKEND_SERVICE" \
  --source backend \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  ${CLOUDSQL_ARGS[@]+"${CLOUDSQL_ARGS[@]}"} \
  --set-env-vars "$ENV_VARS"

BACKEND_URL=$("${GC[@]}" run services describe "$BACKEND_SERVICE" \
  --region "$REGION" --format='value(status.url)') \
  || { echo "ERROR: 取得 $BACKEND_SERVICE URL 失敗" >&2; exit 1; }
[ -n "$BACKEND_URL" ] || { echo "ERROR: $BACKEND_SERVICE URL 為空，後端可能未就緒" >&2; exit 1; }
echo "    backend URL = $BACKEND_URL"

echo "==> [3/5] 寫入 frontend/.env.production（指向 backend）"
echo "VITE_API_BASE=$BACKEND_URL" > "$SCRIPT_DIR/frontend/.env.production"

echo "==> [4/5] 部署 frontend"
"${GC[@]}" run deploy "$FRONTEND_SERVICE" \
  --source frontend \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated

FRONTEND_URL=$("${GC[@]}" run services describe "$FRONTEND_SERVICE" \
  --region "$REGION" --format='value(status.url)') \
  || { echo "ERROR: 取得 $FRONTEND_SERVICE URL 失敗" >&2; exit 1; }
# 避免空字串讓下一步把 CORS_ORIGINS 設成 ""（反而擋掉所有來源）
[ -n "$FRONTEND_URL" ] || { echo "ERROR: $FRONTEND_SERVICE URL 為空，無法收斂 CORS" >&2; exit 1; }
echo "    frontend URL = $FRONTEND_URL"

echo "==> [5/5] 收斂 backend CORS_ORIGINS 為 frontend 網址（含新舊兩種 run.app 格式）"
# Cloud Run 同一服務有兩種網址：舊版 {svc}-{hash}-{code}.a.run.app（= status.url）
# 與新版 {svc}-{projectNumber}.{region}.run.app。兩者 origin 不同，CORS 必須同時允許，
# 否則使用者開新格式網址時，瀏覽器會擋掉所有 API（前端顯示「無法連線後端」）。
PROJECT_NUMBER=$("${GC[@]}" projects describe "$PROJECT" --format='value(projectNumber)') \
  || { echo "ERROR: 取得 projectNumber 失敗，無法組出新格式 frontend 網址" >&2; exit 1; }
[ -n "$PROJECT_NUMBER" ] || { echo "ERROR: projectNumber 為空" >&2; exit 1; }
FRONTEND_URL_NEW="https://${FRONTEND_SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app"
# 值含逗號，沿用 ^|^ 自訂分隔，避免逗號被 gcloud 當成多個環境變數的分隔
"${GC[@]}" run services update "$BACKEND_SERVICE" \
  --region "$REGION" \
  --update-env-vars "^|^CORS_ORIGINS=${FRONTEND_URL},${FRONTEND_URL_NEW}"

echo
echo "✅ 完成"
echo "   frontend : $FRONTEND_URL"
echo "   backend  : $BACKEND_URL"
