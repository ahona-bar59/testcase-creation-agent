# Backend image — FastAPI + LangGraph agent (Phase 5)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install deps first for layer caching.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy the application package.
COPY backend-ai/app /app/app

# Persisted improvement data (feedback / run log) lives here; mount a volume in prod.
RUN mkdir -p /app/data
ENV FEEDBACK_PATH=/app/data/feedback.jsonl \
    RUN_LOG_PATH=/app/data/run_log.jsonl \
    LLM_OFFLINE_STUB=true

EXPOSE 8000

# Single worker: the in-memory run registry + checkpointer are per-process.
# For multi-worker, move them to Postgres/Redis first (see Build_Plan Phase 2/5).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
