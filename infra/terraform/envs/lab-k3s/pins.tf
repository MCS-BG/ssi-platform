# Versions read from the live lab on 2026-10-06 (kubectl get nodes -o wide,
# helm list -A, pod imageIDs, ollama list). Helm chart pins live next to the
# releases in ../../apps/helm.tf; node-level pins (k3s, NVIDIA) are in
# infra/ansible/group_vars/all.yml.

locals {
  pins = {
    k3s_version       = "v1.36.4+k3s1"
    ollama_version    = "0.35.1"
    ollama_chat_model = "llama3.2:3b"
    ollama_embed      = "nomic-embed-text:latest"

    # Ollama model IDs as listed by `ollama list` (the tags are mutable upstream;
    # these IDs are what the lab is serving).
    ollama_model_ids = {
      "llama3.2:3b"             = "a80c4f17acd5"
      "nomic-embed-text:latest" = "0a109f422b47"
      "qwen2.5-coder:1.5b"      = "d7372fd82851"
      "qwen3:4b"                = "359d7dd4bcda"
      "granite4.1:3b"           = "6fd349357287"
    }

    # Raw-manifest image (as written in k8s/*.yaml) => digest the lab is running.
    # Applied only when pin_image_digests = true.
    image_digests = {
      "ollama/ollama:latest"                  = "ollama/ollama:latest@sha256:292ee7945dfc3d5840a181f3ab86fedb1e66703e02c8af98b50f4da56b7e278c"
      "pgvector/pgvector:pg17"                = "pgvector/pgvector:pg17@sha256:cf134a767f474095eeba57e0117be8e568e011a63f33fbf252f14c9b760f8e6f"
      "python:3.12-slim"                      = "python:3.12-slim@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9"
      "ghcr.io/open-webui/open-webui:v0.11.4" = "ghcr.io/open-webui/open-webui:v0.11.4@sha256:9591b13f13843c7721c2b8eaf7382846c81b3ffe126526d1888d1fed50c6a33f"
      "ghcr.io/mcs-bg/mcp-server:5144638"     = "ghcr.io/mcs-bg/mcp-server:5144638@sha256:e21c54cce63dcf88dbd339f727179ca3620b0b61605d25ddf25468f2e60a88ab"
      "ghcr.io/mcs-bg/rag-worker:5144638"     = "ghcr.io/mcs-bg/rag-worker:5144638@sha256:d5a844ca2c2226c51e9d4c96b67b00f43c03437dbb34fde04ab099bc5cccc739"
      "ghcr.io/mcs-bg/prompt-guard:6dfc885"   = "ghcr.io/mcs-bg/prompt-guard:6dfc885@sha256:017b7b4ad2f5b58d9d6213b37ee98592e9623be96cba4b8d02586f86753b5399"
    }
  }
}

output "pins" {
  description = "Versions this root reproduces."
  value       = local.pins
}
