from __future__ import annotations

import httpx
import pytest
from fastapi import Request, Response

# --- helpers ------------------------------------------------------------------


def make_mock_client(status: int = 200, body: bytes = b"upstream ok") -> httpx.AsyncClient:
    """Returns an AsyncClient backed by a fake ASGI app."""

    async def upstream_app(scope: dict, receive: object, send: object) -> None:  # type: ignore[misc]
        assert callable(send)
        await send({"type": "http.response.start", "status": status, "headers": []})
        await send({"type": "http.response.body", "body": body})

    transport = httpx.ASGITransport(app=upstream_app)  # type: ignore[arg-type]
    return httpx.AsyncClient(transport=transport, base_url="https://api.anthropic.com")


async def build_request(
    method: str = "POST",
    path: str = "/v1/messages",
    headers: dict[str, str] | None = None,
    body: bytes = b'{"model":"claude-3"}',
) -> Request:
    """Build a FastAPI Request object for testing."""
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": [
            (k.lower().encode(), v.encode())
            for k, v in (headers or {"content-type": "application/json"}).items()
        ],
    }

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)  # type: ignore[arg-type]


# --- construction -------------------------------------------------------------


@pytest.mark.asyncio
async def test_forwarder_constructs_without_error() -> None:
    from src.proxy.forwarder import Forwarder

    client = make_mock_client()
    fwd = Forwarder(client=client)

    assert fwd is not None


# --- forwarding ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_forwarder_returns_response() -> None:
    from src.proxy.forwarder import Forwarder

    fwd = Forwarder(client=make_mock_client(200, b"result"))
    request = await build_request()

    response = await fwd.forward(request, upstream_key="sk-ant-real")

    assert isinstance(response, Response)


@pytest.mark.asyncio
async def test_forwarder_passes_upstream_status_code() -> None:
    from src.proxy.forwarder import Forwarder

    fwd = Forwarder(client=make_mock_client(201, b"created"))
    request = await build_request()

    response = await fwd.forward(request, upstream_key="sk-ant-real")

    assert response.status_code == 201


@pytest.mark.asyncio
async def test_forwarder_passes_upstream_body() -> None:
    from src.proxy.forwarder import Forwarder

    fwd = Forwarder(client=make_mock_client(200, b"upstream body"))
    request = await build_request()

    response = await fwd.forward(request, upstream_key="sk-ant-real")

    assert response.body == b"upstream body"


@pytest.mark.asyncio
async def test_forwarder_swaps_authorization_header() -> None:
    from src.proxy.forwarder import Forwarder

    received_auth: list[str] = []

    async def capturing_app(scope: dict, receive: object, send: object) -> None:  # type: ignore[misc]
        assert callable(send)
        headers = dict(scope.get("headers", []))
        received_auth.append(headers.get(b"x-api-key", b"").decode())
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    transport = httpx.ASGITransport(app=capturing_app)  # type: ignore[arg-type]
    client = httpx.AsyncClient(transport=transport, base_url="https://api.anthropic.com")

    fwd = Forwarder(client=client)
    request = await build_request(
        headers={"x-api-key": "kr-devkey", "content-type": "application/json"}
    )

    await fwd.forward(request, upstream_key="sk-ant-real123")

    assert received_auth
    assert "sk-ant-real123" in received_auth[0]
    assert "kr-devkey" not in received_auth[0]


# --- error handling -----------------------------------------------------------


@pytest.mark.asyncio
async def test_forwarder_raises_forward_error_on_connect_failure() -> None:
    from src.proxy.forwarder import Forwarder, ForwardError

    async def failing_app(scope: dict, receive: object, send: object) -> None:  # type: ignore[misc]
        raise httpx.ConnectError("refused")

    transport = httpx.ASGITransport(app=failing_app)  # type: ignore[arg-type]
    client = httpx.AsyncClient(transport=transport, base_url="https://api.anthropic.com")
    fwd = Forwarder(client=client)
    request = await build_request()

    with pytest.raises(ForwardError):
        await fwd.forward(request, upstream_key="sk-ant-real")


# --- streaming ----------------------------------------------------------------


_STREAM_BODY = b'{"model":"claude-3","stream":true,"messages":[{"role":"user","content":"hi"}]}'


def make_streaming_client(chunks: list[bytes], status: int = 200) -> httpx.AsyncClient:
    """Returns an AsyncClient whose 'upstream' streams the given chunks."""

    async def streaming_app(scope: dict, receive: object, send: object) -> None:  # type: ignore[misc]
        assert callable(send)
        await send({"type": "http.response.start", "status": status, "headers": []})
        for chunk in chunks:
            await send({"type": "http.response.body", "body": chunk, "more_body": True})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    transport = httpx.ASGITransport(app=streaming_app)  # type: ignore[arg-type]
    return httpx.AsyncClient(transport=transport, base_url="https://api.anthropic.com")


@pytest.mark.asyncio
async def test_forwarder_streaming_returns_streaming_response() -> None:
    from starlette.responses import StreamingResponse

    from src.proxy.forwarder import Forwarder

    fwd = Forwarder(client=make_streaming_client([b"data: chunk1\n\n", b"data: chunk2\n\n"]))
    request = await build_request(body=_STREAM_BODY)

    response = await fwd.forward(request, upstream_key="sk-ant-real")

    assert isinstance(response, StreamingResponse)


@pytest.mark.asyncio
async def test_forwarder_streaming_passes_status_code() -> None:
    from src.proxy.forwarder import Forwarder

    fwd = Forwarder(client=make_streaming_client([b"data: ok\n\n"], status=200))
    request = await build_request(body=_STREAM_BODY)

    response = await fwd.forward(request, upstream_key="sk-ant-real")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_forwarder_streaming_delivers_all_chunks() -> None:
    from src.proxy.forwarder import Forwarder

    chunks = [b"data: a\n\n", b"data: b\n\n", b"data: c\n\n"]
    fwd = Forwarder(client=make_streaming_client(chunks))
    request = await build_request(body=_STREAM_BODY)

    response = await fwd.forward(request, upstream_key="sk-ant-real")

    # Consume the streaming body
    collected = b""
    async for chunk in response.body_iterator:  # type: ignore[union-attr]
        collected += chunk

    assert collected == b"".join(chunks)


@pytest.mark.asyncio
async def test_forwarder_non_stream_body_not_streaming_response() -> None:
    """Without stream:true in the body, returns a buffered Response."""
    from fastapi.responses import Response as FastAPIResponse
    from starlette.responses import StreamingResponse

    from src.proxy.forwarder import Forwarder

    fwd = Forwarder(client=make_mock_client(200, b"buffered"))
    request = await build_request(body=b'{"model":"claude-3","messages":[]}')

    response = await fwd.forward(request, upstream_key="sk-ant-real")

    assert not isinstance(response, StreamingResponse)
    assert isinstance(response, FastAPIResponse)
