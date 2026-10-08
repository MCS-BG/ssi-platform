"""Prompt Guard classifier service (Day 7, part 2).

POST /classify {"text": "...", "threshold": 0.5}
  -> {"label": "malicious"|"benign", "malicious_score": 0.97, "chunks": 1, "latency_ms": 21.4, "model": "..."}
GET /healthz -> "ok" once the model is loaded.

Model: meta-llama/Llama-Prompt-Guard-2-22M (or -86M), loaded from the local cache only
(HF_HUB_OFFLINE=1). Inputs longer than the 512-token context are split into overlapping
windows; the highest malicious probability across windows wins.
"""
import os
import time

import torch
from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from transformers import AutoModelForSequenceClassification, AutoTokenizer

MODEL_DIR = os.environ.get("MODEL_DIR", "/cache/models/Llama-Prompt-Guard-2-22M")
MODEL_ID = os.environ.get("MODEL_ID", "meta-llama/Llama-Prompt-Guard-2-22M")
MAX_LEN = int(os.environ.get("MAX_TOKENS", "512"))
STRIDE = int(os.environ.get("STRIDE", "64"))
MAX_CHARS = int(os.environ.get("MAX_CHARS", "20000"))
DEFAULT_THRESHOLD = float(os.environ.get("THRESHOLD", "0.5"))

torch.set_num_threads(int(os.environ.get("TORCH_THREADS", "2")))

tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR)
model.eval()


def _malicious_index() -> int:
    id2label = getattr(model.config, "id2label", None) or {}
    for idx, name in id2label.items():
        if "malicious" in str(name).lower() or "injection" in str(name).lower():
            return int(idx)
    return 1


MALICIOUS_IDX = _malicious_index()


def _encode_windows(text: str) -> dict:
    """Tokenize once, then cut into overlapping windows of MAX_LEN tokens (with CLS/SEP)."""
    ids = tokenizer(text, add_special_tokens=False, verbose=False)["input_ids"]
    body = MAX_LEN - 2
    step = max(body - STRIDE, 1)
    windows = [ids[i:i + body] for i in range(0, max(len(ids) - STRIDE, 1), step)] or [[]]
    cls_id, sep_id = tokenizer.cls_token_id, tokenizer.sep_token_id
    pad_id = tokenizer.pad_token_id or 0
    seqs = [[cls_id] + w + [sep_id] for w in windows]
    width = max(len(x) for x in seqs)
    input_ids = torch.tensor([x + [pad_id] * (width - len(x)) for x in seqs])
    attention = torch.tensor([[1] * len(x) + [0] * (width - len(x)) for x in seqs])
    return {"input_ids": input_ids, "attention_mask": attention}

app = FastAPI(title="prompt-guard", docs_url=None, redoc_url=None, openapi_url=None)


class ClassifyRequest(BaseModel):
    text: str = Field(min_length=1)
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)


@app.get("/healthz", response_class=PlainTextResponse)
def healthz() -> str:
    return "ok"


@app.post("/classify")
def classify(req: ClassifyRequest) -> dict:
    if len(req.text) > MAX_CHARS:
        raise HTTPException(status_code=413, detail=f"text longer than {MAX_CHARS} characters")
    start = time.perf_counter()
    enc = _encode_windows(req.text)
    with torch.inference_mode():
        logits = model(**enc).logits
    probs = torch.softmax(logits, dim=-1)[:, MALICIOUS_IDX]
    score = float(probs.max())
    threshold = DEFAULT_THRESHOLD if req.threshold is None else req.threshold
    return {
        "label": "malicious" if score >= threshold else "benign",
        "malicious_score": round(score, 4),
        "chunks": int(probs.shape[0]),
        "latency_ms": round((time.perf_counter() - start) * 1000, 1),
        "model": MODEL_ID,
    }
