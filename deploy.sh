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

# 用 ^@^ 自訂分隔符，避免值含特殊字元（LINE token 有 +/= ）被當成分隔。
ENV_VARS="^@^DATABASE_URL=sqlite+aiosqlite:////tmp/aria.db@APP_TZ=Asia/Taipei@CORS_ORIGINS=*@ANTHROPIC_API_KEY=${KEY}"

# 選填：LINE（secret 與 token 都備齊才注入；缺任一就維持純網頁模式）
LINE_SECRET=$(grep -E '^LINE_CHANNEL_SECRET=' "$ENV_FILE" | head -n1 | cut -d= -f2-)
LINE_TOKEN=$(grep -E '^LINE_CHANNEL_ACCESS_TOKEN=' "$ENV_FILE" | head -n1 | cut -d= -f2-)
if [ -n "$LINE_SECRET" ] && [ -n "$LINE_TOKEN" ]; then
  ENV_VARS="${ENV_VARS}@LINE_CHANNEL_SECRET=${LINE_SECRET}@LINE_CHANNEL_ACCESS_TOKEN=${LINE_TOKEN}"
  # 白名單與推播目標也要一起帶，否則部署的服務永遠是「不限制」全開狀態，
  # README 要求的鎖定會被部署路徑悄悄繞過（安全洞）。空值代表不設定（維持全開）。
  LINE_ALLOWED=$(grep -E '^LINE_ALLOWED_USER_IDS=' "$ENV_FILE" | head -n1 | cut -d= -f2-)
  LINE_PUSH_ID=$(grep -E '^LINE_PUSH_USER_ID=' "$ENV_FILE" | head -n1 | cut -d= -f2-)
  [ -n "$LINE_ALLOWED" ] && ENV_VARS="${ENV_VARS}@LINE_ALLOWED_USER_IDS=${LINE_ALLOWED}"
  [ -n "$LINE_PUSH_ID" ] && ENV_VARS="${ENV_VARS}@LINE_PUSH_USER_ID=${LINE_PUSH_ID}"
  if [ -n "$LINE_ALLOWED" ]; then
    echo "    （偵測到 LINE 設定，一併注入；白名單已啟用）"
  else
    echo "    （偵測到 LINE 設定，一併注入；⚠️ 未設白名單＝任何人都能對話）"
  fi
fi

"${GC[@]}" run deploy "$BACKEND_SERVICE" \
  --source backend \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
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

echo "==> [5/5] 收斂 backend CORS_ORIGINS 為 frontend 網址"
"${GC[@]}" run services update "$BACKEND_SERVICE" \
  --region "$REGION" \
  --update-env-vars "CORS_ORIGINS=$FRONTEND_URL"

echo
echo "✅ 完成"
echo "   frontend : $FRONTEND_URL"
echo "   backend  : $BACKEND_URL"
