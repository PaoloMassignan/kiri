from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from src.audit.log import AuditLog
from src.filter.pipeline import Decision, FilterPipeline
from src.keys.manager import KeyManager, MissingUpstreamKeyError
from src.proxy.forwarder import Forwarder, ForwardError
from src.proxy.protocols import anthropic, openai
from src.ratelimit.limiter import RateLimiter, RateLimitExceeded
from src.redaction.engine import RedactionEngine

logger = logging.getLogger(__name__)

_ANTHROPIC_PATHS = {"/v1/messages", "/messages"}
_OPENAI_PATHS = {"/v1/chat/completions"}
_MAX_BODY_BYTES = 10 * 1024 * 1024  # 10 MB — rejects oversized payloads before filter runs


def _detect_protocol(path: str) -> str:
    if path in _OPENAI_PATHS:
        return "openai"
    return "anthropic"


def create_app(
    key_manager: KeyManager,
    pipeline: FilterPipeline,
    forwarder: Forwarder,
    redaction_engine: RedactionEngine | None = None,
    audit_log: AuditLog | None = None,
    rate_limiter: RateLimiter | None = None,
    action: str = "sanitize",
    oauth_passthrough: bool = False,
) -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def _limit_body(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        cl = request.headers.get("content-length")
        if cl is not None:
            try:
                if int(cl) > _MAX_BODY_BYTES:
                    return JSONResponse(
                        {"error": "request_too_large"},
                        status_code=413,
                    )
            except ValueError:
                pass
        return await call_next(request)

    async def _handle(request: Request) -> Response:
        # 1. validate auth — accept both x-api-key and Authorization: Bearer
        key = request.headers.get("x-api-key", "")
        if not key:
            auth = request.headers.get("authorization", "")
            if not auth.startswith("Bearer "):
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            key = auth.removeprefix("Bearer ")

        # Determine if this is an OAuth/Anthropic token in passthrough mode.
        # In passthrough mode the original token is forwarded unchanged and
        # the dual-key bypass-prevention guarantee does not apply (REQ-S-010).
        is_passthrough = oauth_passthrough and key_manager.is_oauth_token(key)

        if is_passthrough:
            audit_key = "oauth-passthrough"
        elif key_manager.is_oauth_token(key):
            # OAuth token received but passthrough is disabled — reject as unauthorized
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        elif not key_manager.is_valid(key):
            return JSONResponse({"error": "unauthorized"}, status_code=403)
        else:
            audit_key = key

        # 2. rate limiting (per key, after auth so we have a valid key)
        if rate_limiter is not None and not is_passthrough:
            try:
                rate_limiter.check(key)
            except RateLimitExceeded as exc:
                return JSONResponse(
                    {"error": "rate_limit_exceeded", "retry_after": exc.retry_after},
                    status_code=429,
                )

        # 3. detect protocol and extract prompt
        _path = request.url.path
        protocol = _detect_protocol(_path)
        body_bytes = await request.body()
        body_override: bytes | None = None

        if _path in _ANTHROPIC_PATHS | _OPENAI_PATHS:
            try:
                body = json.loads(body_bytes)
            except Exception:
                body = {}

            extractor = openai if protocol == "openai" else anthropic
            prompt = extractor.extract_prompt(body)
            result = pipeline.run(prompt)

            # When action="block", escalate any REDACT decision to BLOCK
            # (no forwarding at all — the request is rejected with HTTP 403).
            if action == "block" and result.decision == Decision.REDACT:
                result = type(result)(
                    decision=Decision.BLOCK,
                    reason=result.reason,
                    top_similarity=result.top_similarity,
                    matched_symbols=result.matched_symbols,
                    matched_file=result.matched_file,
                )

            # Run redaction before logging so we can store the forwarded prompt.
            redacted_prompt = ""
            if result.decision == Decision.REDACT and redaction_engine is not None:
                redaction = redaction_engine.redact(prompt)
                if redaction.was_redacted:
                    body = extractor.replace_prompt(body, redaction.redacted_prompt)
                    body_override = json.dumps(body).encode()
                    redacted_prompt = redaction.redacted_prompt

            if audit_log is not None:
                audit_log.record(result, prompt, key=audit_key, redacted_prompt=redacted_prompt)

            if result.decision == Decision.BLOCK:
                return JSONResponse(
                    {"error": "blocked", "reason": result.reason},
                    status_code=403,
                )

        # 4. get upstream key and forward
        # In passthrough mode the original token is the upstream credential.
        if is_passthrough:
            upstream_key = key
        else:
            try:
                upstream_key = key_manager.get_upstream_key(protocol=protocol)
            except MissingUpstreamKeyError:
                env_var = "OPENAI_API_KEY" if protocol == "openai" else "ANTHROPIC_API_KEY"
                logger.error("proxy: %s not configured", env_var)
                return JSONResponse({"error": "upstream key not configured"}, status_code=503)

        try:
            return await forwarder.forward(
                request, upstream_key,
                body_override=body_override,
                protocol=protocol,
            )
        except ForwardError as exc:
            logger.error("proxy: forward error: %s", exc)
            return JSONResponse({"error": "forward failed"}, status_code=502)

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    app.add_route("/v1/messages", _handle, methods=["POST"])
    app.add_route("/messages", _handle, methods=["POST"])
    app.add_route("/v1/chat/completions", _handle, methods=["POST"])
    app.add_route("/{path:path}", _handle, methods=["GET", "POST", "PUT", "DELETE", "PATCH"])

    return app
