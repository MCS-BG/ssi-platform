# ssi-langgraph (Day 17): the SSI agent as a LangGraph graph, next to the control layer.
# Build context is the REPOSITORY ROOT, because the image reuses apps/control-layer/server.py
# (the graph calls its Prompt Guard, MCP slot, model backend and memory functions):
#   docker build -f apps/ssi-langgraph/Dockerfile -t ssi-langgraph .
# Built for linux/amd64. The lab runs the same files from a ConfigMap (k8s/day-17-ssi-langgraph.yaml).
FROM python:3.12.14-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LANGSMITH_TRACING=false \
    LANGCHAIN_TRACING_V2=false

WORKDIR /app
COPY apps/ssi-langgraph/requirements.txt ./
RUN pip install --no-cache-dir --disable-pip-version-check --only-binary=:all: --no-deps -r requirements.txt
COPY apps/control-layer/server.py ./control_layer.py
COPY apps/ssi-langgraph/cl_bridge.py apps/ssi-langgraph/graph.py apps/ssi-langgraph/server.py ./

USER 10001:10001
EXPOSE 8080
CMD ["python", "/app/server.py"]
