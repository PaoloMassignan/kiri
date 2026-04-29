from __future__ import annotations

import httpx
import pytest
from fastapi import Request, Response

from src.filter.pipeline import Decision, FilterResult
from src.keys.manager import MissingUpstreamKeyError

# --- fakes --------------------------------------------------------------------


class FakeKeyManager:
    def __init__(self, valid_keys: set[str], upstream: str = "sk-ant-real") -> None:
        self._valid = valid_keys
        self._upstream = upstream

    def is_valid(self, key: str) -> bool:
        return key in self._valid

    def get_upstream_key(self, protocol: str = "anthropic") -> str:
        if not self._upstream:
            raise MissingUpstreamKeyError("no key")
        return self._upstream


class FakePipeline:
    def __init__(self, decision: Decision, reason: str = "test reason") -> None:
        self._result = FilterResult(
            decision=decision,
            reason=reason,
            top_similarity=0.5,
        )

    def run(self, prompt: str) -> FilterResult:
        return self._result


class FakeForwarder:
    def __init__(self, status: int = 200, body: bytes = b'{"id":"msg_1"}') -> None:
        self._status = status
        self._body = body
        self.forwarded_key: str | None = None

    async def forward(
        self, request: Request, upstream_key: str,
        body_override: bytes | None = None, protocol: str = "anthropic",
    ) -> Response:
        self.forwarded_key = upstream_key
        return Response(content=self._body, status_code=self._status)


def make_client(
    valid_keys: set[str] | None = None,
    decision: Decision = Decision.PASS,
    reason: str = "below threshold",
    upstream: str = "sk-ant-real",
    forwarder: FakeForwarder | None = None,
) -> httpx.AsyncClient:
    from src.proxy.server import create_app

    km = FakeKeyManager(valid_keys or {"kr-valid"}, upstream=upstream)
    pipeline = FakePipeline(decision=decision, reason=reason)
    fwd = forwarder or FakeForwarder()
    app = create_app(
        key_manager=km,  # type: ignore[arg-type]
        pipeline=pipeline,  # type: ignore[arg-type]
        forwarder=fwd,  # type: ignore[arg-type]
    )
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


_VALID_BODY = b'{"model":"claude-3","messages":[{"role":"user","content":"hello"}]}'


# --- construction -------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_app_returns_fastapi_app() -> None:
    from fastapi import FastAPI

    from src.proxy.server import create_app

    app = create_app(
        key_manager=FakeKeyManager(set()),  # type: ignore[arg-type]
        pipeline=FakePipeline(Decision.PASS),  # type: ignore[arg-type]
        forwarder=FakeForwarder(),  # type: ignore[arg-type]
    )

    assert isinstance(app, FastAPI)


# --- authentication -----------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_auth_header_returns_401() -> None:
    async with make_client() as client:
        response = await client.post("/v1/messages", content=_VALID_BODY)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_malformed_auth_header_returns_401() -> None:
    async with make_client() as client:
        response = await client.post(
            "/v1/messages",
            content=_VALID_BODY,
            headers={"Authorization": "kr-valid"},  # missing "Bearer "
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_invalid_gateway_key_returns_403() -> None:
    async with make_client(valid_keys={"kr-valid"}) as client:
        response = await client.post(
            "/v1/messages",
            content=_VALID_BODY,
            headers={"Authorization": "Bearer kr-unknown"},
        )

    assert response.status_code == 403


# --- filter pipeline ----------------------------------------------------------


@pytest.mark.asyncio
async def test_blocked_prompt_returns_403() -> None:
    async with make_client(decision=Decision.BLOCK, reason="symbol match: Foo") as client:
        response = await client.post(
            "/v1/messages",
            content=_VALID_BODY,
            headers={"Authorization": "Bearer kr-valid"},
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_blocked_response_body_contains_reason() -> None:
    async with make_client(decision=Decision.BLOCK, reason="symbol match: Foo") as client:
        response = await client.post(
            "/v1/messages",
            content=_VALID_BODY,
            headers={"Authorization": "Bearer kr-valid"},
        )

    data = response.json()
    assert data["error"] == "blocked"
    assert "Foo" in data["reason"]


@pytest.mark.asyncio
async def test_passed_prompt_is_forwarded() -> None:
    fwd = FakeForwarder(status=200, body=b'{"id":"msg_ok"}')
    async with make_client(decision=Decision.PASS, forwarder=fwd) as client:
        response = await client.post(
            "/v1/messages",
            content=_VALID_BODY,
            headers={"Authorization": "Bearer kr-valid"},
        )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_passed_prompt_uses_upstream_key() -> None:
    fwd = FakeForwarder()
    async with make_client(
        decision=Decision.PASS, upstream="sk-ant-secret", forwarder=fwd
    ) as client:
        await client.post(
            "/v1/messages",
            content=_VALID_BODY,
            headers={"Authorization": "Bearer kr-valid"},
        )

    assert fwd.forwarded_key == "sk-ant-secret"


# --- action=block escalates REDACT to BLOCK -----------------------------------


@pytest.mark.asyncio
async def test_action_block_escalates_redact_to_403() -> None:
    from src.proxy.server import create_app

    km = FakeKeyManager({"kr-valid"})
    pipeline = FakePipeline(decision=Decision.REDACT, reason="symbol match: foo")
    fwd = FakeForwarder()
    app = create_app(
        key_manager=km,  # type: ignore[arg-type]
        pipeline=pipeline,  # type: ignore[arg-type]
        forwarder=fwd,  # type: ignore[arg-type]
        action="block",
    )
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/messages",
            content=_VALID_BODY,
            headers={"Authorization": "Bearer kr-valid"},
        )

    assert response.status_code == 403
    assert response.json()["error"] == "blocked"


# --- missing upstream key -----------------------------------------------------


@pytest.mark.asyncio
async def test_missing_upstream_key_returns_503() -> None:
    async with make_client(decision=Decision.PASS, upstream="") as client:
        response = await client.post(
            "/v1/messages",
            content=_VALID_BODY,
            headers={"Authorization": "Bearer kr-valid"},
        )

    assert response.status_code == 503


# --- 401 response body --------------------------------------------------------


@pytest.mark.asyncio
async def test_unauthorized_response_has_error_field() -> None:
    async with make_client() as client:
        response = await client.post("/v1/messages", content=_VALID_BODY)

    assert response.json()["error"] == "unauthorized"


# --- health endpoint ----------------------------------------------------------


@pytest.mark.asyncio
async def test_health_endpoint_returns_200() -> None:
    async with make_client() as client:
        response = await client.get("/health")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_endpoint_no_auth_required() -> None:
    """Health check must not require a gateway key (used by Docker healthcheck)."""
    async with make_client(valid_keys=set()) as client:
        response = await client.get("/health")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_endpoint_returns_ok_body() -> None:
    async with make_client() as client:
        response = await client.get("/health")

    assert response.json() == {"status": "ok"}


# --- body size limit ----------------------------------------------------------


@pytest.mark.asyncio
async def test_oversized_request_returns_413() -> None:
    """POST with Content-Length > 10 MB must be rejected before filter runs."""
    oversized = b"x" * (11 * 1024 * 1024)  # 11 MB

    async with make_client(decision=Decision.PASS) as client:
        response = await client.post(
            "/v1/messages",
            content=oversized,
            headers={"x-api-key": "kr-valid"},
        )

    assert response.status_code == 413
    assert response.json()["error"] == "request_too_large"


@pytest.mark.asyncio
async def test_normal_request_not_rejected_by_size_limit() -> None:
    """A normal-sized request must pass the size check."""
    fwd = FakeForwarder()

    async with make_client(decision=Decision.PASS, forwarder=fwd) as client:
        response = await client.post(
            "/v1/messages",
            content=_VALID_BODY,
            headers={"x-api-key": "kr-valid"},
        )

    assert response.status_code != 413


@pytest.mark.asyncio
async def test_size_limit_checked_before_auth() -> None:
    """413 must be returned even for unauthenticated requests (no key leaked)."""
    oversized = b"x" * (11 * 1024 * 1024)

    async with make_client() as client:
        response = await client.post(
            "/v1/messages",
            content=oversized,
            # no x-api-key header
        )

    assert response.status_code == 413
