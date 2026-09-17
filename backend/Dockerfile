# Backend image for Railway (or any container host).
#
# Railway builds this automatically when it finds a Dockerfile in the service's
# root directory. Nothing here is Railway-specific: the same image runs on
# Render, Fly, or a plain VM.

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

# Railway injects PORT. Locally it falls back to 8000.
# Shell form so ${PORT} is expanded.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
