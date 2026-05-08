"""Minimal mock LLM server for E2E tests.

Accepts Anthropic /v1/messages and OpenAI /v1/chat/completions requests,
saves each request body as JSON to MOCK_PAYLOAD_DIR, and returns a fixed
response. Never inspects content — it is a pure recorder.

Usage:
    MOCK_PAYLOAD_DIR=/tmp/payloads MOCK_PORT=9999 python mock_llm.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

PAYLOAD_DIR = Path(os.environ.get("MOCK_PAYLOAD_DIR", "/tmp/mock_llm_payloads"))
PORT = int(os.environ.get("MOCK_PORT", "9999"))

app = FastAPI()
_counter = 0

_ANTHROPIC_RESPONSE = {
    "id": "msg_mock",
    "type": "message",
    "role": "assistant",
    "content": [{"type": "text", "text": "Mock response: safe refactor suggestion."}],
    "model": "claude-sonnet-4-6",
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 10, "output_tokens": 8},
}

_OPENAI_RESPONSE = {
    "id": "chatcmpl-mock",
    "object": "chat.completion",
    "choices": [{
        "index": 0,
        "message": {"role": "assistant", "content": "Mock response: safe refactor suggestion."},
        "finish_reason": "stop",
    }],
    "usage": {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18},
}


def _save(body: object) -> Path:
    global _counter
    _counter += 1
    PAYLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = PAYLOAD_DIR / f"request_{_counter:04d}.json"
    path.write_text(json.dumps(body, indent=2), encoding="utf-8")
    return path


@app.post("/v1/messages")
@app.post("/messages")
async def anthropic_messages(request: Request) -> JSONResponse:
    body = await request.json()
    saved = _save(body)
    print(f"[mock] /v1/messages -> {saved}", flush=True)
    return JSONResponse(_ANTHROPIC_RESPONSE)


@app.post("/v1/chat/completions")
async def openai_completions(request: Request) -> JSONResponse:
    body = await request.json()
    saved = _save(body)
    print(f"[mock] /v1/chat/completions -> {saved}", flush=True)
    return JSONResponse(_OPENAI_RESPONSE)


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "requests_received": _counter})


if __name__ == "__main__":
    PAYLOAD_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[mock] starting on port {PORT}, payloads -> {PAYLOAD_DIR}", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
