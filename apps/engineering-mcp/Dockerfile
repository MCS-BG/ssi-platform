# engineering-mcp: GitHub repos/issues/PRs/code/commits (read-only) or the Day 10 sample, JSON-RPC at /mcp.
# Built for linux/amd64. Day 10 lab also runs this file from a ConfigMap.
FROM python:3.12.14-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY server.py ./

USER 10001:10001
EXPOSE 8000
CMD ["python", "/app/server.py"]
