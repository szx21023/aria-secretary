FROM python:3.11-slim

WORKDIR /app

# 先裝依賴（利用 layer cache）
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

# Alembic migration：啟動時 init_db 會跑 upgrade head，需這兩者在 image 內
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini

# Cloud Run 會以 $PORT 注入埠號（預設 8080）
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
