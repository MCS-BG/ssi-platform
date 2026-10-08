# rag-worker: a toolbox pod for the Day 4 RAG scripts (ask.py, ingest.py).
# Packages are installed at build time, so the pod no longer pip-installs on start.
# Built for linux/amd64 by .github/workflows/build-rag-worker.yml.
FROM python:3.12.14-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --only-binary=:all: -r requirements.txt

COPY *.py ./

USER 10001:10001
CMD ["sleep", "infinity"]
