# Backend image. Built by Render (render.yaml), Fly.io (fly.toml) or any
# container host; nothing here is host specific.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first, on their own layer, so a code change does not
# reinstall every package.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

# Render and Fly inject PORT. Locally it falls back to 8000.
# Shell form so ${PORT} is expanded.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
