"""E2E scenario runner.

Loads scenarios.yaml, executes each scenario against a running Kiri proxy,
reads payloads saved by mock_llm.py, and asserts redaction correctness.

Usage:
    python run_scenarios.py \\
        --scenarios tests/e2e/scenarios.yaml \\
        --fixtures-dir benchmarks/real-projects/fixtures \\
        --workspace /tmp/kiri-e2e \\
        --kiri-url http://localhost:8765 \\
        --kiri-key kr-... \\
        --mock-payload-dir /tmp/mock_llm_payloads \\
        --kiri-dir kiri \\
        [--suite easy|full]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml  # pyyaml


# ── helpers ──────────────────────────────────────────────────────────────────

def _load_yaml(path: Path) -> object:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _find_case(fixture: dict, case_id: str) -> dict:
    for case in fixture.get("cases", []) + fixture.get("hard_cases", []):
        if case["id"] == case_id:
            return case
    raise ValueError(f"case '{case_id}' not found in fixture")


def _payload_count(payload_dir: Path) -> int:
    return len(list(payload_dir.glob("request_*.json")))


def _latest_payload(payload_dir: Path, before_count: int) -> str | None:
    """Return the raw JSON text of the first new payload file written after before_count."""
    files = sorted(payload_dir.glob("request_*.json"))
    new_files = files[before_count:]
    if not new_files:
        return None
    return new_files[0].read_text(encoding="utf-8")


def _kiri_exec(kiri_dir: str, *args: str) -> str:
    cmd = ["docker", "compose", "--project-directory", kiri_dir, "exec", "-T", "kiri", "kiri", *args]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"kiri {' '.join(args)} failed:\n{result.stderr}")
    return result.stdout.strip()


def _post(url: str, body: dict, key: str) -> tuple[int, dict]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "x-api-key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _wait_for_symbol(kiri_dir: str, symbol: str, timeout: int = 30) -> bool:
    """Poll kiri status until the @symbol entry appears (max timeout seconds).

    Note: kiri status lists explicit @symbol entries under "Symbols".
    File-extracted symbols are NOT listed by name — only @symbol entries are.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            out = _kiri_exec(kiri_dir, "status")
            # @symbol entries show up as bare names in the status output
            if symbol in out:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


# ── main ─────────────────────────────────────────────────────────────────────

def run(
    scenarios_path: Path,
    fixtures_dir: Path,
    workspace: Path,
    kiri_url: str,
    kiri_key: str,
    payload_dir: Path,
    kiri_dir: str,
    suite: str,
) -> bool:
    scenarios_doc = _load_yaml(scenarios_path)
    scenarios = scenarios_doc["scenarios"]

    passed = 0
    failed = 0
    skipped = 0
    failures: list[str] = []

    for s in scenarios:
        sid = s["id"]
        s_suite = s.get("suite", "easy")

        if s_suite == "full" and suite == "easy":
            print(f"  SKIP  {sid}  (full suite only)")
            skipped += 1
            continue

        fixture_path = fixtures_dir / s["fixture"] / "fixture.yaml"
        if not fixture_path.exists():
            print(f"  SKIP  {sid}  (fixture not found: {fixture_path})")
            skipped += 1
            continue

        fixture = _load_yaml(fixture_path)
        try:
            case = _find_case(fixture, s["case"])
        except ValueError as exc:
            print(f"  FAIL  {sid}  {exc}")
            failed += 1
            failures.append(f"{sid}: {exc}")
            continue

        assertions = s["assertions"]
        prompt: str = case["prompt"]

        # Write source files to workspace so Kiri can index them
        workspace.mkdir(parents=True, exist_ok=True)
        protected_symbols: list[str] = [
            s["text"] for s in fixture.get("protected_symbols", [])
        ]
        written_files: list[str] = []
        for sf in fixture.get("source_files", []):
            dest = workspace / sf["filename"]
            dest.write_text(sf["content"], encoding="utf-8")
            written_files.append(sf["filename"])

        # Register files AND explicit symbols with kiri.
        # `kiri add <file>` queues async indexing (L1 vectors + symbol extraction).
        # `kiri add @Symbol` registers the symbol immediately in L2 — no embedding needed.
        # Both are called so the E2E test verifies the kiri add CLI for both paths.
        kiri_add_ok = True
        for filename in written_files:
            try:
                _kiri_exec(kiri_dir, "add", filename)
            except Exception as exc:
                print(f"  FAIL  {sid}  kiri add {filename} failed: {exc}")
                failed += 1
                failures.append(f"{sid}: kiri add failed: {exc}")
                kiri_add_ok = False
                break

        if kiri_add_ok:
            for sym in protected_symbols:
                try:
                    _kiri_exec(kiri_dir, "add", f"@{sym}")
                except Exception as exc:
                    print(f"  WARN  {sid}  kiri add @{sym} failed: {exc}")

        if kiri_add_ok:
            # Poll until first protected symbol appears in kiri status (max 15s)
            first_symbol = protected_symbols[0] if protected_symbols else None
            if first_symbol:
                if not _wait_for_symbol(kiri_dir, first_symbol, timeout=15):
                    print(f"  WARN  {sid}  symbol '{first_symbol}' not yet in kiri status after 15s")

            # Count payloads before the request
            before = _payload_count(payload_dir)

            # Send request to Kiri
            body = {
                "model": "claude-sonnet-4-6",
                "max_tokens": 100,
                "messages": [{"role": "user", "content": prompt}],
            }
            http_status, _resp = _post(f"{kiri_url}/v1/messages", body, kiri_key)

            expected_http = assertions.get("expected_http", 200)
            if http_status != expected_http:
                msg = f"HTTP {http_status} != expected {expected_http}"
                print(f"  FAIL  {sid}  {msg}")
                failed += 1
                failures.append(f"{sid}: {msg}")
                continue

            # Read the payload the mock received
            time.sleep(0.5)  # give mock a moment to flush to disk
            payload_text = _latest_payload(payload_dir, before)

            if payload_text is None and expected_http == 200:
                msg = "no payload received by mock (request not forwarded?)"
                print(f"  FAIL  {sid}  {msg}")
                failed += 1
                failures.append(f"{sid}: {msg}")
                continue

            if payload_text is None:
                # BLOCK case: no forwarding expected
                print(f"  PASS  {sid}")
                passed += 1
                continue

            # Assert must_not_contain
            fail_reason: str | None = None
            for forbidden in assertions.get("must_not_contain", []):
                if forbidden in payload_text:
                    fail_reason = f"payload contains forbidden string: {forbidden!r}"
                    break

            # Assert must_contain_stub
            if fail_reason is None:
                stub_marker = "[PROTECTED:"
                stub_present = stub_marker in payload_text
                must_have_stub = assertions.get("must_contain_stub", False)
                if must_have_stub and not stub_present:
                    fail_reason = f"payload missing stub marker '{stub_marker}'"
                elif not must_have_stub and stub_present:
                    fail_reason = f"payload has unexpected stub marker (PASS scenario should be unchanged)"

            if fail_reason:
                print(f"  FAIL  {sid}  {fail_reason}")
                failed += 1
                failures.append(f"{sid}: {fail_reason}")
            else:
                print(f"  PASS  {sid}")
                passed += 1

            continue  # next scenario

    # Summary
    total = passed + failed + skipped
    print(f"\n{'─' * 50}")
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped / {total} total")
    if failures:
        print("\nFailures:")
        for f in failures:
            print(f"  - {f}")

    return failed == 0


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--scenarios", required=True)
    p.add_argument("--fixtures-dir", required=True)
    p.add_argument("--workspace", required=True)
    p.add_argument("--kiri-url", required=True)
    p.add_argument("--kiri-key", required=True)
    p.add_argument("--mock-payload-dir", required=True)
    p.add_argument("--kiri-dir", required=True)
    p.add_argument("--suite", default="easy", choices=["easy", "full"])
    args = p.parse_args()

    ok = run(
        scenarios_path=Path(args.scenarios),
        fixtures_dir=Path(args.fixtures_dir),
        workspace=Path(args.workspace),
        kiri_url=args.kiri_url,
        kiri_key=args.kiri_key,
        payload_dir=Path(args.mock_payload_dir),
        kiri_dir=args.kiri_dir,
        suite=args.suite,
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
