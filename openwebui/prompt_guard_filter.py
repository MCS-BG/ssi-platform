"""
title: Prompt Guard
author: ai-ops-homelab
version: 0.8.1
description: Blocks chat messages that Llama Prompt Guard 2 scores as prompt injection or jailbreak.
"""

# Day 8b: Open WebUI Filter function. Paste this file into Admin Panel > Functions > Create.
# Its inlet sends the newest user message to the Day 7 Prompt Guard service and aborts the turn
# (Open WebUI shows the error in the chat) when malicious_score >= threshold.
# Standard library only, so there is no "requirements" line and nothing is pip-installed.
# Docs: https://docs.openwebui.com/features/extensibility/plugin/functions/filter

import asyncio
import json
import urllib.request

from pydantic import BaseModel, Field

MAX_CHARS = 20000  # the classifier answers 413 above this (MAX_CHARS in apps/prompt-guard)


def _last_user_text(messages):
    """Text of the newest user message; content can be a string or a list of parts."""
    for message in reversed(messages or []):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(part.get("text", "") for part in content
                             if isinstance(part, dict) and part.get("type") == "text")
        return ""
    return ""


def _pieces(text):
    if len(text) <= MAX_CHARS:
        return [text]
    step = MAX_CHARS - 1000
    return [text[i:i + MAX_CHARS] for i in range(0, len(text), step)]


class Filter:
    class Valves(BaseModel):
        priority: int = Field(default=0, description="Lower runs first. 0 = before other filters.")
        url: str = Field(default="http://prompt-guard.si-lab.svc.cluster.local:8080/classify",
                         description="Prompt Guard /classify endpoint")
        threshold: float = Field(default=0.5, ge=0.0, le=1.0,
                                 description="Block at or above this malicious_score (0.5 = model decision point)")
        fail_closed: bool = Field(default=True,
                                  description="Block the message if Prompt Guard cannot be reached")
        timeout_seconds: float = Field(default=10.0, description="HTTP timeout per call")

    def __init__(self):
        self.valves = self.Valves()

    def _score(self, text):
        best = None
        for piece in _pieces(text):
            request = urllib.request.Request(
                self.valves.url,
                data=json.dumps({"text": piece, "threshold": self.valves.threshold}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=self.valves.timeout_seconds) as response:
                result = json.load(response)
            if best is None or float(result["malicious_score"]) > float(best["malicious_score"]):
                best = result
        return best

    async def inlet(self, body: dict, __user__: dict | None = None,
                    __metadata__: dict | None = None) -> dict:
        if (__metadata__ or {}).get("task"):
            return body  # internal task calls (title, tags, follow-ups) reuse text that was already checked
        text = _last_user_text(body.get("messages")).strip()
        if not text:
            return body
        try:
            result = await asyncio.to_thread(self._score, text)
        except Exception as e:
            if self.valves.fail_closed:
                raise Exception(f"Prompt Guard unavailable, message blocked ({type(e).__name__}).")
            print(f"prompt_guard: classifier unreachable, message allowed: {type(e).__name__}")
            return body
        score = float(result["malicious_score"])
        print(f"prompt_guard: malicious_score={score:.4f} threshold={self.valves.threshold}")
        if score >= self.valves.threshold:
            raise Exception(
                f"Blocked by Prompt Guard: this message looks like a prompt injection or jailbreak "
                f"(malicious_score {score:.3f} >= threshold {self.valves.threshold}). "
                f"Rephrase it, or start a new chat."
            )
        return body
