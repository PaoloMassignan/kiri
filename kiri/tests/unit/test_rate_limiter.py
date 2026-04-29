from __future__ import annotations

from unittest.mock import patch

import pytest

from src.ratelimit.limiter import RateLimiter, RateLimitExceeded


class TestRateLimiterDisabled:

    def test_disabled_by_default(self):
        rl = RateLimiter()
        assert not rl.enabled

    def test_zero_rpm_never_raises(self):
        rl = RateLimiter(rpm=0)
        for _ in range(1000):
            rl.check("kr-key")  # must not raise

    def test_disabled_flag(self):
        assert not RateLimiter(rpm=0).enabled
        assert RateLimiter(rpm=60).enabled


class TestRateLimiterAllowed:

    def test_requests_within_limit_pass(self):
        rl = RateLimiter(rpm=5)
        for _ in range(5):
            rl.check("kr-key")  # no exception

    def test_single_request_always_passes(self):
        rl = RateLimiter(rpm=1)
        rl.check("kr-key")

    def test_different_keys_independent(self):
        rl = RateLimiter(rpm=2)
        rl.check("kr-key-a")
        rl.check("kr-key-a")
        rl.check("kr-key-b")  # separate bucket, must not raise
        rl.check("kr-key-b")


class TestRateLimiterBlocked:

    def test_exceeding_limit_raises(self):
        rl = RateLimiter(rpm=3)
        for _ in range(3):
            rl.check("kr-key")
        with pytest.raises(RateLimitExceeded):
            rl.check("kr-key")

    def test_exception_has_retry_after(self):
        rl = RateLimiter(rpm=1)
        rl.check("kr-key")
        with pytest.raises(RateLimitExceeded) as exc_info:
            rl.check("kr-key")
        assert exc_info.value.retry_after >= 1

    def test_retry_after_is_positive(self):
        rl = RateLimiter(rpm=1)
        rl.check("kr-key")
        with pytest.raises(RateLimitExceeded) as exc_info:
            rl.check("kr-key")
        assert exc_info.value.retry_after > 0

    def test_key_a_blocked_does_not_block_key_b(self):
        rl = RateLimiter(rpm=1)
        rl.check("kr-key-a")
        with pytest.raises(RateLimitExceeded):
            rl.check("kr-key-a")
        rl.check("kr-key-b")  # must not raise


class TestSlidingWindow:

    def test_old_requests_leave_window(self):
        """Timestamps older than 60s should be dropped, freeing up budget."""
        rl = RateLimiter(rpm=2)
        fake_now = 1000.0

        with patch("src.ratelimit.limiter.time.monotonic", return_value=fake_now):
            rl.check("kr-key")
            rl.check("kr-key")

        # advance time by 61 seconds — old entries fall outside window
        with patch("src.ratelimit.limiter.time.monotonic", return_value=fake_now + 61.0):
            rl.check("kr-key")  # must not raise — window is clear

    def test_requests_at_window_edge_still_count(self):
        """Timestamps exactly at window_start boundary should be dropped."""
        rl = RateLimiter(rpm=1)
        fake_now = 1000.0

        with patch("src.ratelimit.limiter.time.monotonic", return_value=fake_now):
            rl.check("kr-key")

        # 59 seconds later — still in window
        with patch("src.ratelimit.limiter.time.monotonic", return_value=fake_now + 59.0):
            with pytest.raises(RateLimitExceeded):
                rl.check("kr-key")

    def test_retry_after_reflects_window_remaining(self):
        """retry_after should reflect how long until the oldest entry expires."""
        rl = RateLimiter(rpm=1)
        fake_now = 1000.0

        with patch("src.ratelimit.limiter.time.monotonic", return_value=fake_now):
            rl.check("kr-key")

        # 10 seconds later — oldest entry was at t=1000, window is 60s
        # so it expires at t=1060, meaning ~50s remain
        with patch("src.ratelimit.limiter.time.monotonic", return_value=fake_now + 10.0):
            with pytest.raises(RateLimitExceeded) as exc_info:
                rl.check("kr-key")
        assert exc_info.value.retry_after <= 51  # ≤51s (1 second buffer)
        assert exc_info.value.retry_after >= 49


class TestServerIntegration:

    @pytest.mark.asyncio
    async def test_429_when_limit_exceeded(self):
        """Requests beyond rpm limit return HTTP 429."""
        import json
        import os
        import shutil
        import tempfile
        from unittest.mock import MagicMock

        import httpx

        from src.filter.pipeline import Decision, FilterResult
        from src.keys.manager import KeyManager
        from src.proxy.server import create_app

        tmp = tempfile.mkdtemp()
        os.environ.setdefault("ANTHROPIC_API_KEY", "fake")
        try:
            km = KeyManager(keys_dir=__import__("pathlib").Path(tmp) / "keys")
            key = km.create_key()

            pipeline = MagicMock()
            pipeline.run.return_value = FilterResult(
                decision=Decision.PASS, reason="below threshold", top_similarity=0.1
            )

            from fastapi.responses import Response as FResponse

            class _FakeForwarder:
                async def forward(self, *a, **kw):
                    return FResponse(content=b"{}", status_code=200)

            forwarder = _FakeForwarder()

            rl = RateLimiter(rpm=2)
            app = create_app(key_manager=km, pipeline=pipeline,
                             forwarder=forwarder, rate_limiter=rl)

            transport = httpx.ASGITransport(app=app)
            client = httpx.AsyncClient(transport=transport, base_url="http://testserver")

            body = json.dumps({"model": "claude-3-5-sonnet-20241022",
                               "messages": [{"role": "user", "content": "hi"}]}).encode()

            r1 = await client.post("/v1/messages", content=body, headers={"x-api-key": key})
            r2 = await client.post("/v1/messages", content=body, headers={"x-api-key": key})
            r3 = await client.post("/v1/messages", content=body, headers={"x-api-key": key})

            assert r1.status_code != 429
            assert r2.status_code != 429
            assert r3.status_code == 429
            assert r3.json()["error"] == "rate_limit_exceeded"
            assert "retry_after" in r3.json()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_health_not_rate_limited(self):
        """GET /health never touches the rate limiter."""
        import os
        import shutil
        import tempfile
        from unittest.mock import MagicMock

        import httpx

        from src.keys.manager import KeyManager
        from src.proxy.server import create_app

        tmp = tempfile.mkdtemp()
        os.environ.setdefault("ANTHROPIC_API_KEY", "fake")
        try:
            km = KeyManager(keys_dir=__import__("pathlib").Path(tmp) / "keys")
            pipeline = MagicMock()
            forwarder = MagicMock()

            rl = RateLimiter(rpm=1)
            app = create_app(key_manager=km, pipeline=pipeline,
                             forwarder=forwarder, rate_limiter=rl)

            transport = httpx.ASGITransport(app=app)
            client = httpx.AsyncClient(transport=transport, base_url="http://testserver")

            for _ in range(10):
                r = await client.get("/health")
                assert r.status_code == 200
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
