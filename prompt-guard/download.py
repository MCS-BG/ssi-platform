"""Init step: fetch the gated Prompt Guard model into the cache PVC once."""
import os
import sys

from huggingface_hub import snapshot_download

model_id = os.environ["MODEL_ID"]
model_dir = os.environ["MODEL_DIR"]
if os.path.exists(os.path.join(model_dir, "config.json")):
    print(f"model cached in {model_dir}")
    sys.exit(0)
token = os.environ.get("HF_TOKEN") or None
if token is None:
    sys.exit("HF_TOKEN missing: create the hf-token Secret (see docs/day-07-observability-steps.md)")
snapshot_download(
    repo_id=model_id,
    local_dir=model_dir,
    token=token,
    allow_patterns=["*.json", "*.safetensors", "*.model", "*.txt"],
)
print(f"downloaded {model_id} to {model_dir}")
