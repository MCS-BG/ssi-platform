# ssi-gateway: private front door (/control + /mcp) for the SSI Connector.
# Built for linux/amd64. The Day 11 lab runs the same server.py from a ConfigMap.
FROM python:3.12.14-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY server.py ./

USER 10001:10001
EXPOSE 8080
CMD ["python", "/app/server.py"]
