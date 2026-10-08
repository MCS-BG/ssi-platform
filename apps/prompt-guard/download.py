"""Init step: fetch the gated Prompt Guard model into the cache PVC once.

The model is never part of the container image. It is gated on Hugging Face, and the
image is public, so baking it in would redistribute it.
"""
import os
import shutil
import sys

from huggingface_hub import snapshot_download

# Day 8a: packages now live in the image. If LEGACY_DEPS_DIR is set, remove the old
# pip target folder that the Day 7 init container left on the PVC (~1.2 GB).
legacy = os.environ.get("LEGACY_DEPS_DIR")
if legacy and os.path.isdir(legacy):
    shutil.rmtree(legacy, ignore_errors=True)
    shutil.rmtree(os.path.join(os.path.dirname(legacy), ".pip-tmp"), ignore_errors=True)
    print(f"removed legacy deps folder {legacy}")

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
