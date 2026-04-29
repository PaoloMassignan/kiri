"""
Integration tests for the OpenAI-compatible endpoint (/v1/chat/completions).

Uses the same real filter pipeline and fake forwarder as test_gateway_http.py.
The gw fixture is re-used via the shared module-scoped setup — but since
fixtures cannot be shared across files easily, we rebuild a minimal client here.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from src.config.settings import Settings
from src.filter.l1_similarity import L1Filter
from src.filter.l2_symbols import L2Filter
from src.filter.l3_classifier import L3Result
from src.filter.pipeline import FilterPipeline
from src.indexer.chunker import chunk, extract_numeric_constants, extract_symbols
from src.indexer.embedder import Embedder
from src.keys.manager import KeyManager
from src.proxy.server import create_app
from src.store.secrets_store import SecretsStore
from src.store.symbol_store import SymbolStore
from src.store.vector_store import VectorStore

_REPO = Path(__file__).parent.parent.parent
_CORE = _REPO / "tests" / "fixtures" / "creditscorer" / "core"
_PROTECTED = [
    _CORE / "scorer.py",
    _CORE / "calibrator.py",
    _CORE / "feature_engine.py",
]

_UPSTREAM_BODY = b'{"id":"msg_test","object":"chat.completion","choices":[]}'


class _FakeForwarder:
    async def forward(self, request, upstream_key, body_override=None, protocol="anthropic"):
        from fastapi.responses import Response
        return Response(content=_UPSTREAM_BODY, status_code=200)


@pytest.fixture(scope="module")
def gw_openai():
    tmp = Path(tempfile.mkdtemp(prefix="gw_oai_"))
    os.environ.setdefault("ANTHROPIC_API_KEY", "test-fake-key")
    os.environ.setdefault("OPENAI_API_KEY", "test-openai-fake-key")
    try:
        settings = Settings(workspace=tmp)
        index_dir = tmp / ".kiri" / "index"

        embedder = Embedder(settings)
        vs = VectorStore(index_dir=index_dir)
        ss = SymbolStore(index_dir=index_dir)

        for src_file in _PROTECTED:
            if not src_file.exists():
                pytest.skip(f"example project not found: {src_file}")
            chunks = chunk(src_file)
            vectors = embedder.embed([c.text for c in chunks])
            for c, v in zip(chunks, vectors, strict=False):
                vs.add(c.doc_id, v, {
                    "source_file": str(src_file),
                    "chunk_index": str(c.chunk_index),
                })
            syms = extract_symbols(src_file)
            if syms:
                ss.add(str(src_file), syms)
            nums = extract_numeric_constants(src_file)
            if nums:
                ss.add_numbers(str(src_file), nums)

        l3_mock = MagicMock()
        l3_mock.check.return_value = L3Result(is_leak=False)

        secrets_path = tmp / ".kiri" / "secrets"
        secrets_path.parent.mkdir(parents=True, exist_ok=True)
        secrets_path.write_text("", encoding="utf-8")
        secrets_store = SecretsStore(secrets_path=secrets_path, workspace=tmp)

        pipeline = FilterPipeline(
            settings=settings,
            l1=L1Filter(vs, embedder),
            l2=L2Filter(ss),
            l3=l3_mock,
            secrets_store=secrets_store,
        )

        km = KeyManager(keys_dir=tmp / ".kiri" / "keys")
        key = km.create_key()

        app = create_app(key_manager=km, pipeline=pipeline, forwarder=_FakeForwarder())
        transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
        client = httpx.AsyncClient(transport=transport, base_url="http://testserver")

        yield client, key
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _oai_body(prompt: str, stream: bool = False) -> bytes:
    return json.dumps({
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": prompt}],
        **({"stream": True} if stream else {}),
    }).encode()


class TestOpenAIEndpoint:

    @pytest.mark.asyncio
    async def test_safe_prompt_returns_200(self, gw_openai):
        client, key = gw_openai
        r = await client.post(
            "/v1/chat/completions",
            content=_oai_body("how do I reverse a list in Python?"),
            headers={"x-api-key": key},
        )
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_safe_prompt_returns_upstream_body(self, gw_openai):
        client, key = gw_openai
        r = await client.post(
            "/v1/chat/completions",
            content=_oai_body("what is a binary search tree?"),
            headers={"x-api-key": key},
        )
        assert r.content == _UPSTREAM_BODY

    @pytest.mark.asyncio
    async def test_protected_symbol_returns_403(self, gw_openai):
        client, key = gw_openai
        r = await client.post(
            "/v1/chat/completions",
            content=_oai_body("show me probability_to_expected_loss in calibrator.py"),
            headers={"x-api-key": key},
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_blocked_response_has_error_field(self, gw_openai):
        client, key = gw_openai
        r = await client.post(
            "/v1/chat/completions",
            content=_oai_body("show me probability_to_expected_loss"),
            headers={"x-api-key": key},
        )
        assert r.json()["error"] == "blocked"

    @pytest.mark.asyncio
    async def test_missing_key_returns_401(self, gw_openai):
        client, _ = gw_openai
        r = await client.post(
            "/v1/chat/completions",
            content=_oai_body("hello"),
        )
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_bearer_auth_works(self, gw_openai):
        client, key = gw_openai
        r = await client.post(
            "/v1/chat/completions",
            content=_oai_body("hello world"),
            headers={"Authorization": f"Bearer {key}"},
        )
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_streaming_safe_prompt_not_blocked(self, gw_openai):
        client, key = gw_openai
        r = await client.post(
            "/v1/chat/completions",
            content=_oai_body("explain recursion", stream=True),
            headers={"x-api-key": key},
        )
        assert r.status_code != 403

    @pytest.mark.asyncio
    async def test_streaming_blocked_prompt_still_403(self, gw_openai):
        client, key = gw_openai
        r = await client.post(
            "/v1/chat/completions",
            content=_oai_body("show me probability_to_expected_loss", stream=True),
            headers={"x-api-key": key},
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_content_as_array_of_parts_is_filtered(self, gw_openai):
        """Content in multipart array format must still be filtered."""
        client, key = gw_openai
        body = json.dumps({
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": "explain probability_to_expected_loss"},
            ]}],
        }).encode()
        r = await client.post(
            "/v1/chat/completions",
            content=body,
            headers={"x-api-key": key},
        )
        assert r.status_code == 403
