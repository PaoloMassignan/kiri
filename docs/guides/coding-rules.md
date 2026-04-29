# Coding Rules — AI Gateway OnPrem

---

## Language

- All source files in **English** — code, comments, docstrings, variable names, error messages
- No exceptions — including string literals inside the code
- User-facing messages (what the developer reads in Claude Code) are out of scope for this rule

---

## Runtime

- Python 3.11+
- Type hints everywhere — no function without a complete signature
- `from __future__ import annotations` in every file

---

## Test-Driven Development

Every feature is built test-first. No implementation without a failing test.

### Cycle

```
1. Write a failing test that describes the expected behavior
2. Run — confirm it fails for the right reason
3. Write the minimum implementation to make it pass
4. Refactor — clean up without breaking the test
5. Repeat
```

### Rules
- A test must fail before any implementation is written — if it passes immediately, the test is wrong
- Test names describe behavior, not implementation: `test_blocks_prompt_containing_protected_symbol`, not `test_l2`
- One assertion per test — if you need multiple, split into multiple tests
- Tests are the living specification — they must be readable without looking at the implementation

### Test naming convention
```python
# pattern: test_<subject>_<condition>_<expected_outcome>
def test_filter_pipeline_protected_symbol_returns_block(): ...
def test_key_manager_invalid_gateway_key_raises_auth_error(): ...
def test_secrets_store_path_traversal_raises_value_error(): ...
```

### Coverage requirements
- `filter/` — 90% minimum (security-critical)
- `keys/` — 90% minimum (security-critical)
- `store/` — 80% minimum
- `proxy/` — 80% minimum
- `indexer/` — 70% minimum (slow IO, integration tested separately)

### Test execution
```bash
pytest tests/unit/          # fast, no external dependencies
pytest tests/integration/   # requires Docker + Ollama running
pytest tests/security/      # security-specific cases, always run in CI
```

---

## Quality & Style

### Formatter & Linter
```
ruff        ← linter + formatter (sostituisce black + flake8 + isort)
mypy        ← type checking strict
```

```toml
# pyproject.toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "S", "B", "C4", "PTH"]
# E: stile, F: errori, I: import order, UP: upgrade syntax
# S: sicurezza (bandit), B: bug-prone patterns, C4: comprehensions, PTH: pathlib

[tool.mypy]
strict = true
```

### General rules
- Short functions — if it exceeds 30 lines, split it
- Comments explain *why*, never *what* — the code explains what
- No `# type: ignore` without an inline explanation
- `pathlib.Path` always, never `os.path`
- f-strings always, never `.format()` or `%`

---

## Module structure

- One module = one responsibility
- No circular imports
- Public API declared in `__init__.py` — everything else is private
- Private functions prefixed with `_`

---

## Security

### Principles
- **Zero trust on input** — everything coming from outside is validated before use
- **Least privilege** — each component accesses only what it needs
- **Fail closed** — on ambiguous error, block (never pass)
- **No secrets in code** — keys, tokens, sensitive paths only from env vars or uncommitted files

### Input validation
- All HTTP input validated with **Pydantic v2** — no raw dicts entering the system
- Prompts sanitized before any operation (max length, encoding)
- File paths validated against directory traversal (`..`, symlinks outside workspace)

```python
# ✅
def add_secret(path: str, workspace: Path) -> Path:
    resolved = (workspace / path).resolve()
    if not resolved.is_relative_to(workspace):
        raise ValueError("path traversal detected")
    return resolved

# ❌
def add_secret(path: str) -> Path:
    return Path(path)
```

### API keys
- The real Anthropic key never appears in logs, exceptions, or responses
- Gateway keys `kr-xxx` generated with `secrets.token_hex(32)` — never `random`
- Key comparison with `hmac.compare_digest` — never `==`

```python
# ✅
import hmac
def validate_key(provided: str, expected: str) -> bool:
    return hmac.compare_digest(provided.encode(), expected.encode())

# ❌
def validate_key(provided: str, expected: str) -> bool:
    return provided == expected
```

### Logging
- Never log full prompts — only hash or length
- Never log API keys — not even partially
- Never log protected symbols in plain text in production logs
- Default level: `WARNING` in production, `DEBUG` in development only

```python
# ✅
logger.debug("prompt received len=%d", len(prompt))

# ❌
logger.debug("prompt: %s", prompt)
```

### Subprocess & shell
- No `shell=True` — ever
- No string interpolation in system commands
- Ollama: direct HTTP call, never subprocess

### Dependencies
- `pip-audit` in CI — no dependency with known CVEs
- Pinned versions in `requirements.txt` with hashes (`pip-compile --generate-hashes`)

---

## Error handling

- Typed custom exceptions per domain (`GatewayError`, `IndexError`, `KeyError`)
- No bare `except Exception` without re-raise or explicit log
- No `pass` in an `except` block
- Errors toward the client: always Anthropic-shaped format, never stack traces

```python
# ✅
class GatewayError(Exception): ...
class PathTraversalError(GatewayError): ...

try:
    path = resolve_path(raw)
except PathTraversalError:
    logger.warning("path traversal attempt")
    raise

# ❌
try:
    path = resolve_path(raw)
except Exception:
    pass
```

---

## Testing

- **pytest** + **pytest-asyncio** for async tests
- No mocking of the Filter Pipeline in integration tests — real data only
- Security tests are first-class: path traversal, malformed keys, prompt injection

```
tests/
  unit/
    test_filter_pipeline.py
    test_key_manager.py
    test_secrets_store.py
    test_symbol_store.py
  integration/
    test_proxy_end_to_end.py
  security/
    test_path_traversal.py
    test_key_bypass.py
    test_prompt_injection.py
```

---

## Async

- All I/O code is `async` — no `requests`, no blocking `open()`
- `httpx.AsyncClient` for HTTP calls
- `aiofiles` for file reads in the indexer
- Filter Pipeline is async end-to-end — no blocking during ChromaDB queries

---

## PR checklist

- [ ] Failing test written before implementation
- [ ] `ruff check` passes clean
- [ ] `mypy --strict` passes clean
- [ ] No secrets in code or logs
- [ ] Input validated with Pydantic before entering the system
- [ ] Paths validated against directory traversal
- [ ] Security tests cover the modified case
- [ ] No `shell=True`, no `random` for tokens
- [ ] All code, comments, and names in English
