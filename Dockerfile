# Backend image: FastAPI + ML deps (CPU-only, works on amd64 and arm64)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# System libraries required by the Python deps:
#  - tesseract-ocr / libgl / libglib : OpenCV headless + pytesseract OCR
#  - build-essential          : compiling wheels (lightgbm, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        libgl1 \
        libglib2.0-0 \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first for better layer caching.
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the application source.
COPY app ./app

# Copy Alembic migration config (used by `alembic upgrade head`).
COPY alembic ./alembic
COPY alembic.ini .

# tini ensures SIGTERM/SIGINT are forwarded so uvicorn/worker shut down cleanly.
RUN pip install tini

EXPOSE 8000

ENTRYPOINT ["tini", "--"]
# Single worker: the app uses module-level singletons + background tasks
# (see P2 #10). Use the `worker` service (not `--workers N`) to scale ingest.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
