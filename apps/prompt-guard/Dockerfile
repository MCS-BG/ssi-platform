# prompt-guard: the Day 7 Prompt Guard 2 classifier (FastAPI on :8080, CPU-only torch).
# The model is NOT in this image. It is gated on Hugging Face and this image is public,
# so the init container (download.py) keeps it on the prompt-guard-cache PVC instead.
# Built for linux/amd64 by .github/workflows/build-prompt-guard.yml.
FROM python:3.12.14-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HUB_DISABLE_TELEMETRY=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --only-binary=:all: -r requirements.txt

COPY *.py ./

USER 10001:10001
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "server:app", "--app-dir", "/app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
