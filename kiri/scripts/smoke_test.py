#!/usr/bin/env python3
"""
Gateway smoke test -- no real Anthropic key needed.

Starts the gateway in-process on port 8766, creates a gateway key,
and exercises four scenarios:

  1. 401  -- no Authorization header
  2. 403  -- wrong / unknown key
  3. 403  -- valid key but prompt contains a protected @symbol
  4. 502  -- valid key, clean prompt -> gateway forwards, gets connection error
             (no real Anthropic behind it -- proves the request reached the proxy)

Usage:
  py -3.11 scripts/smoke_test.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import logging
import uvicorn

# Silence expected 502 error log from scenario 4
logging.getLogger("src.proxy.server").setLevel(logging.CRITICAL)

# Make sure we can import src.*
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.settings import Settings
from src.filter.l1_similarity import L1Result
from src.filter.l2_symbols import L2Filter, L2Result
from src.filter.l3_classifier import L3Result
from src.filter.pipeline import FilterPipeline
from src.keys.manager import KeyManager
from src.proxy.forwarder import Forwarder
from src.proxy.server import create_app
from src.store.symbol_store import SymbolStore

PORT = 8766
BASE = f"http://localhost:{PORT}"
SYMBOL = "SecretAlgo"

# ── colours ───────────────────────────────────────────────────────────────────

GREEN = "\033[32m"
RED   = "\033[31m"
CYAN  = "\033[36m"
RESET = "\033[0m"


def ok(label: str, detail: str = "") -> None:
    print(f"  {GREEN}PASS{RESET}  {label}" + (f"  ({detail})" if detail else ""))


def fail(label: str, detail: str = "") -> None:
    print(f"  {RED}FAIL{RESET}  {label}" + (f"  ({detail})" if detail else ""))
    sys.exit(1)


def section(title: str) -> None:
    print(f"\n{CYAN}{title}{RESET}")


# ── fakes (same pattern as unit tests) ────────────────────────────────────────


class _FakeL1:
    """Always returns score 0.0 -- nothing in the vector store."""

    def check(self, prompt: str) -> L1Result:
        return L1Result(top_score=0.0, top_doc_id="", top_source_file="")


class _FakeL3:
    """Always passes -- Ollama not needed."""

    def check(self, prompt: str) -> L3Result:
        return L3Result(is_leak=False)


# ── gateway bootstrap ──────────────────────────────────────────────────────────


def _build_gateway(tmp: Path) -> tuple[object, str]:
    settings = Settings(
        similarity_threshold=0.75,
        hard_block_threshold=0.90,
        proxy_port=PORT,
    )

    keys_dir   = tmp / "keys"
    symbol_dir = tmp / "symbols"

    key_mgr   = KeyManager(keys_dir=keys_dir)
    gw_key    = key_mgr.create_key()

    symbol_dir.mkdir(parents=True, exist_ok=True)
    sym_store = SymbolStore(index_dir=symbol_dir)
    sym_store.add_explicit([SYMBOL])

    l2       = L2Filter(symbol_store=sym_store)
    pipeline = FilterPipeline(
        settings=settings,
        l1=_FakeL1(),   # type: ignore[arg-type]
        l2=l2,
        l3=_FakeL3(),   # type: ignore[arg-type]
    )

    # Custom httpx client pointing nowhere -- ensures scenario 4 gets 502
    bad_client  = httpx.AsyncClient(base_url="http://localhost:19999", timeout=2.0)
    forwarder   = Forwarder(client=bad_client)

    os.environ.setdefault("ANTHROPIC_API_KEY", "fake-key-for-smoke-test")

    app = create_app(
        key_manager=key_mgr,
        pipeline=pipeline,
        forwarder=forwarder,
    )
    return app, gw_key


# ── server thread ─────────────────────────────────────────────────────────────


def _start_server(app: object) -> None:
    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="critical")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            httpx.get(f"{BASE}/health", timeout=0.5)
            return
        except Exception:
            time.sleep(0.1)
    fail("server did not start within 10 s")


# ── scenarios ─────────────────────────────────────────────────────────────────


def _post(*, auth: str | None = None, content: str = "hello") -> httpx.Response:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if auth is not None:
        headers["Authorization"] = f"Bearer {auth}"
    body = {
        "model": "claude-3-5-haiku-20241022",
        "max_tokens": 16,
        "messages": [{"role": "user", "content": content}],
    }
    return httpx.post(f"{BASE}/v1/messages", headers=headers, json=body, timeout=5)


def run_scenarios(gw_key: str) -> None:

    section("Scenario 1 -- no Authorization -> 401")
    r = _post(auth=None)
    if r.status_code == 401:
        ok("401 received", r.json().get("error", ""))
    else:
        fail("expected 401", str(r.status_code))

    section("Scenario 2 -- wrong key -> 403")
    r = _post(auth="kr-totally-wrong-key")
    if r.status_code == 403:
        ok("403 received", r.json().get("error", ""))
    else:
        fail("expected 403", str(r.status_code))

    section(f"Scenario 3 -- valid key + '{SYMBOL}' in prompt -> 403 blocked")
    r = _post(auth=gw_key, content=f"explain {SYMBOL} to me")
    if r.status_code == 403:
        reason = r.json().get("reason", "")
        ok("403 received", reason)
    else:
        fail("expected 403", f"got {r.status_code}: {r.text[:120]}")

    section("Scenario 4 -- valid key + clean prompt -> 502 (no upstream)")
    r = _post(auth=gw_key, content="what is 2+2?")
    if r.status_code == 502:
        ok("502 received -- prompt reached proxy, upstream unreachable (expected)")
    else:
        fail("expected 502", f"got {r.status_code}: {r.text[:120]}")


# ── main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    print(f"\nGateway smoke test -- port {PORT}")
    print("=" * 48)

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        app, gw_key = _build_gateway(tmp)
        print(f"\nGateway key : {CYAN}{gw_key}{RESET}")
        print(f"Protected   : {CYAN}@{SYMBOL}{RESET}")

        _start_server(app)
        run_scenarios(gw_key)

    print(f"\n{GREEN}All scenarios passed.{RESET}\n")


if __name__ == "__main__":
    main()
