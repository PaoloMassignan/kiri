# Functional Requirements — EARS Format

Requirements ID prefix: `REQ-F-`

See [`README.md`](README.md) for EARS template reference and traceability notes.

---

## REQ-F-001: Transparent interception

```
WHEN a developer tool sends an HTTP request to the gateway port,
the gateway SHALL authenticate the request using a kr- key
before forwarding it upstream.

WHEN a developer tool sends an HTTP request WITHOUT a valid kr- key,
the gateway SHALL return HTTP 401 with body {"error": "unauthorized"}.

WHILE a request is authenticated and the filter pipeline returns PASS,
the gateway SHALL forward the request to the upstream API
and stream the response back to the caller unchanged.
```

**User story:** US-01 (install), US-02 (protect)
**Tests:** `tests/unit/test_server.py`, `tests/integration/test_gateway_http.py`

---

## REQ-F-002: File protection

```
WHEN a developer runs "kiri add <path>",
the gateway SHALL add the file path to .kiri/secrets
and trigger re-indexing of the file.

WHEN a developer runs "kiri add <path>" and the path already exists in secrets,
the gateway SHALL perform no write and return a confirmation message.

WHEN a developer runs "kiri add @Symbol",
the gateway SHALL add the symbol to .kiri/secrets as an @symbol entry
and make the symbol immediately active for L2 filtering without requiring re-indexing.

WHEN a developer runs "kiri add <directory>/" or "kiri add <glob>",
the gateway SHALL store a single @glob rule in .kiri/secrets
and index all files currently matching the pattern.

WHEN new files appear in a directory protected by a @glob rule,
the gateway SHALL index them automatically within 60 seconds
without requiring any manual command.
```

**User story:** US-02, US-14
**Tests:** `tests/unit/test_cli_add.py`, `tests/unit/test_secrets_store.py`

---

## REQ-F-003: Protection removal

```
WHEN a developer runs "kiri rm <path>",
the gateway SHALL remove the path from .kiri/secrets
and purge the corresponding vectors from the index.

WHEN a developer runs "kiri rm <directory>/" or "kiri rm <glob>",
the gateway SHALL remove the @glob rule from .kiri/secrets
and purge vectors and symbols for all files that were indexed from that rule,
except files that are also individually listed in secrets.

WHEN a developer runs "kiri rm @Symbol",
the gateway SHALL remove the symbol from .kiri/secrets.

WHEN a developer runs "kiri rm <path>" and the path does not exist in secrets,
the gateway SHALL return without error.
```

**User story:** US-03
**Tests:** `tests/unit/test_cli_remove.py`, `tests/unit/test_secrets_store.py`

---

## REQ-F-004: Protection status

```
WHEN a developer runs "kiri status",
the gateway SHALL display: the list of @glob rules (with file count each),
the list of individually protected paths, the list of protected symbols,
the total number of indexed chunks, and the total number of known symbols.
```

**User story:** US-04, US-14
**Tests:** `tests/unit/test_cli_status.py`

---

## REQ-F-005: Prompt inspection (dry-run)

```
WHEN a developer runs "kiri inspect <text>",
the gateway SHALL run the full filter pipeline against the text
and display: the decision (PASS/BLOCK/REDACT), the filter level that triggered,
the top similarity score, and the matched symbols if any.

WHEN a developer runs "kiri inspect --file <path>",
the gateway SHALL read the prompt from the file
instead of from the command-line argument.
```

**User story:** US-05
**Security rationale:** `--file` avoids storing sensitive code in shell history.
**Tests:** `tests/unit/test_cli_inspect.py`, `tests/unit/test_cli_app.py`

---

## REQ-F-006: Automatic indexing

```
WHILE the gateway is running,
WHEN .kiri/secrets is modified (by git pull, kiri add, or kiri rm),
the gateway SHALL re-index the affected files in the background
without requiring a restart.

WHEN the gateway starts,
the gateway SHALL index all files listed in .kiri/secrets (individual paths and
@glob expansions) that have not yet been indexed.

WHILE the gateway is running and @glob rules are active,
the gateway SHALL re-expand each rule every 60 seconds and index any new files
that have appeared since the last scan.
```

**User story:** US-06, US-10, US-14
**Tests:** `tests/unit/test_watcher.py`, `tests/unit/test_initial_index.py`

---

## REQ-F-007: Audit log

```
WHEN the filter pipeline produces a decision (PASS, BLOCK, or REDACT),
the gateway SHALL append a JSONL entry to .kiri/audit.log containing:
timestamp (ISO 8601 UTC), decision, filter level, reason, top similarity score,
matched symbols, and key_id (first 12 characters of the requesting kr- key).

The gateway SHALL NOT store the full prompt text in the audit log.
The gateway SHALL store at most 120 characters of the prompt in the audit log.

WHEN a developer runs "kiri log",
the gateway SHALL display the last 50 audit entries.

WHEN a developer runs "kiri log --decision <PASS|BLOCK|REDACT>",
the gateway SHALL display only entries matching the specified decision.

WHEN a developer runs "kiri log --since <today|yesterday|YYYY-MM-DD>",
the gateway SHALL display only entries from the specified date onward.
```

**User story:** US-09
**Tests:** `tests/unit/test_audit_log.py`

---

## REQ-F-008: Per-key rate limiting

```
WHILE a kr- key sends requests,
the gateway SHALL enforce a per-key sliding-window rate limit.

WHEN a kr- key exceeds the rate limit,
the gateway SHALL return HTTP 429 with body {"error": "rate_limit_exceeded"}.
```

**User story:** US-12
**Tests:** `tests/unit/test_rate_limiter.py`

---

## REQ-F-009: OpenAI protocol

```
WHEN a developer tool sends a request to POST /v1/chat/completions,
the gateway SHALL extract the prompt text using OpenAI message format,
apply the filter pipeline, and forward or block accordingly.
```

**User story:** US-11
**Tests:** `tests/unit/test_openai_protocol.py`, `tests/integration/test_gateway_openai.py`

---

## REQ-F-010: REDACT decision in the grace zone

```
WHILE a request has L1 similarity in the range [0.75, 0.90)
AND L2 symbol match returns no match
AND L3 classifier returns PASS,
the gateway SHALL replace protected function bodies with stub comments
before forwarding the request to upstream.
```

**User story:** US-02 (note), US-07
**ADR:** [ADR-006](../adr/ADR-006-redact-vs-block.md)
**Tests:** `tests/unit/test_redaction.py`, `tests/unit/test_pipeline.py`

---

## REQ-F-011: Summary management

```
WHEN a developer runs "kiri summary list",
the gateway SHALL display all protected symbols that have a stored summary,
showing: symbol name, source (ollama/manual), and the first line of the summary.
WHEN no summaries exist, the gateway SHALL display "(no summaries)".

WHEN a developer runs "kiri summary show <symbol>",
the gateway SHALL display the full current summary for that symbol,
including source and updated timestamp.
WHEN the symbol has no summary, the gateway SHALL exit with code 1
and display "No summary found for: <symbol>".

WHEN a developer runs "kiri summary set <symbol> <text>",
the gateway SHALL store the text as the manual summary for that symbol,
marking source=manual and recording the current UTC timestamp.
WHEN the text contains numeric literals that may reveal proprietary constants,
the gateway SHALL emit a warning before storing.

WHEN a developer runs "kiri summary reset <symbol>",
the gateway SHALL remove the manual override for that symbol if one exists
and fall back to the Ollama-generated summary.
WHEN no Ollama summary exists, the gateway SHALL attempt to regenerate via Ollama
using the stored chunk text.
WHEN Ollama is unavailable during reset, the gateway SHALL exit with code 1
and preserve the existing summary unchanged.

WHEN a developer runs "kiri summary reset --all",
the gateway SHALL regenerate all summaries via Ollama for all indexed chunks.

In the REDACT engine, manual summaries SHALL take priority over
Ollama-generated summaries for the same symbol.
```

**User story:** US-13
**Tests:** `tests/unit/test_summary_cli.py`
