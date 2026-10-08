# control-layer: guarded agent loop across the business, engineering and productivity MCP slots.
# Built for linux/amd64. The lab also runs server.py from a ConfigMap (k8s/day-15-control-layer-memory.yaml).
FROM python:3.12.14-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt ./
# Day 15: psycopg (binary wheel) for conversation memory.
RUN pip install --no-cache-dir --disable-pip-version-check --only-binary=:all: -r requirements.txt
COPY server.py ./

USER 10001:10001
EXPOSE 8080
CMD ["python", "/app/server.py"]
