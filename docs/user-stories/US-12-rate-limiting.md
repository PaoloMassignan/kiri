# US-12 — Rate limiting per kiri key

## Description

**As** a gateway administrator,
**I want** to limit the number of requests each key can make per minute,
**so that** a compromised key or a runaway script cannot saturate
the gateway or generate uncontrolled costs on the upstream API.

---

## Scenario

A developer leaves the key `kr-abc123` in an unsupervised test script.
The script runs in a loop and sends 500 requests per minute.

Without rate limiting: all requests pass through to the upstream, cost = 500 × API rate.

With rate limiting configured at 60 rpm:

```
POST /v1/messages  →  200 OK        (requests 1–60)
POST /v1/messages  →  429 Too Many Requests  (request 61+)

HTTP 429
{"error": "rate_limit_exceeded", "retry_after": 12}
```

The `retry_after` field indicates the seconds to wait before the window empties.

---

## Expected behaviour

- The limit is configurable in `config.yaml` via `rate_limit_rpm` (0 = disabled)
- The counter is per kiri key — different keys have independent buckets
- The window is sliding (not fixed) — avoids bursts at the minute boundary
- Requests to `/health` do not consume the budget
- If the gateway restarts, counters are reset (in-memory, not persistent)

---

## Acceptance criteria

- [ ] Requests within the limit → pass through normally
- [ ] Request over the limit → 429 with `{"error": "rate_limit_exceeded", "retry_after": N}`
- [ ] `rate_limit_rpm = 0` disables rate limiting entirely
- [ ] Per-key counters: different keys do not affect each other
- [ ] `/health` is not counted
- [ ] `retry_after` is calculated correctly (seconds until the oldest entry expires)

---

## Notes

Recommended implementation: sliding window with a deque of timestamps per key.
No external dependencies — just `collections.deque` and `time.monotonic()`.
Simplicity beats precision: an in-memory approximation is sufficient for this use case.
