# m365-mcp: Microsoft 365 (Graph) productivity MCP, Streamable HTTP on :8000.
# Starts through opentelemetry-instrument; the OTEL_* settings come from the Deployment.
# Built for linux/amd64 by .github/workflows/build-m365-mcp.yml.
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
EXPOSE 8000
CMD ["opentelemetry-instrument", "python", "/app/server.py"]
