from __future__ import annotations

import json
import os

import httpx
from fastapi import Request, Response
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse

_ANTHROPIC_BASE = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
_HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
}
# Auth headers from the client — always replaced with upstream key
# content-length is stripped so httpx recomputes it from the actual body
# (body may have been shortened by the redaction engine)
_STRIP_AUTH = {"authorization", "x-api-key", "host", "accept-encoding", "content-length"}


class ForwardError(Exception):
    pass


class Forwarder:
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        openai_base: str = "https://api.openai.com",
    ) -> None:
        self._anthropic_client = client or httpx.AsyncClient(
            base_url=_ANTHROPIC_BASE,
            timeout=httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0),
        )
        self._openai_client = httpx.AsyncClient(
            base_url=openai_base,
            timeout=httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0),
        )
        # backward-compat alias
        self._client = self._anthropic_client

    async def forward(
        self,
        request: Request,
        upstream_key: str,
        body_override: bytes | None = None,
        protocol: str = "anthropic",
    ) -> Response:
        headers = {
            k: v
            for k, v in request.headers.items()
            if k.lower() not in _HOP_BY_HOP and k.lower() not in _STRIP_AUTH
        }
        if protocol == "openai" or upstream_key.startswith("sk-ant-oat01-"):
            headers["authorization"] = f"Bearer {upstream_key}"
        else:
            headers["x-api-key"] = upstream_key
        headers["accept-encoding"] = "identity"  # no compression — we forward as-is

        body = body_override if body_override is not None else await request.body()

        # Normalize path: /messages -> /v1/messages (some SDKs omit the /v1 prefix)
        path = request.url.path
        if path == "/messages":
            path = "/v1/messages"
        url = path
        if request.url.query:
            url = f"{url}?{request.url.query}"

        # Detect streaming requests — use SSE streaming response to avoid buffering.
        is_stream = False
        try:
            is_stream = bool(json.loads(body).get("stream", False))
        except Exception:  # noqa: S110
            pass

        client = self._openai_client if protocol == "openai" else self._anthropic_client

        try:
            if is_stream:
                return await self._forward_stream(request.method, url, headers, body, client)
            else:
                return await self._forward_buffered(request.method, url, headers, body, client)
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError) as exc:
            raise ForwardError(str(exc)) from exc

    async def _forward_buffered(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        client: httpx.AsyncClient | None = None,
    ) -> Response:
        c = client or self._anthropic_client
        upstream = await c.request(
            method=method,
            url=url,
            headers=headers,
            content=body,
        )
        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            headers={
                k: v for k, v in upstream.headers.items()
                if k.lower() not in _HOP_BY_HOP
            },
        )

    async def _forward_stream(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        client: httpx.AsyncClient | None = None,
    ) -> StreamingResponse:
        c = client or self._anthropic_client
        req = c.build_request(method, url, headers=headers, content=body)
        upstream = await c.send(req, stream=True)
        return StreamingResponse(
            content=upstream.aiter_bytes(),
            status_code=upstream.status_code,
            headers={
                k: v for k, v in upstream.headers.items()
                if k.lower() not in _HOP_BY_HOP
            },
            background=BackgroundTask(upstream.aclose),
        )
