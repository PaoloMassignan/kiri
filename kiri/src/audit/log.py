from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.filter.pipeline import FilterResult

_EXCERPT_LEN = 120


def _level_from_reason(reason: str) -> str:
    if reason.startswith("symbol match:"):
        return "L2"
    if reason.startswith("classifier:") or reason == "grace zone: no signal":
        return "L3"
    return "L1"


@dataclass
class AuditEntry:
    timestamp: str
    decision: str
    reason: str
    level: str
    top_similarity: float
    matched_symbols: list[str]
    prompt_excerpt: str
    key_id: str = ""              # first 12 chars of kr- key; empty if not provided
    matched_file: str = ""        # source file that triggered L1 similarity
    redacted_prompt: str = ""     # full prompt as forwarded to LLM (empty for BLOCK/PASS)


class AuditLog:
    def __init__(
        self,
        log_path: Path,
        max_bytes: int = 0,
        backup_count: int = 5,
    ) -> None:
        """
        Args:
            log_path:     Path to the active log file.
            max_bytes:    Rotate when the file exceeds this size.
                          0 (default) disables rotation.
            backup_count: How many rotated files to keep
                          (audit.log.1 … audit.log.N).
        """
        self._path = log_path
        self._max_bytes = max_bytes
        self._backup_count = max(backup_count, 1)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record(
        self,
        result: FilterResult,
        prompt: str,
        key: str = "",
        redacted_prompt: str = "",
    ) -> None:
        entry = AuditEntry(
            timestamp=datetime.now(tz=UTC).isoformat(timespec="seconds"),
            decision=result.decision.value.upper(),
            reason=result.reason,
            level=_level_from_reason(result.reason),
            top_similarity=round(result.top_similarity, 4),
            matched_symbols=list(result.matched_symbols),
            prompt_excerpt=prompt[:_EXCERPT_LEN],
            key_id=key[:12],  # enough to identify which key, not enough to reuse it
            matched_file=result.matched_file,
            redacted_prompt=redacted_prompt,
        )
        line = json.dumps(asdict(entry), ensure_ascii=False)
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            if self._should_rotate():
                self._rotate()
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def tail(self, n: int = 50) -> list[AuditEntry]:
        """Return the last *n* entries across current and rotated files.

        Pass n=0 to return all entries.
        """
        files = self._all_log_files()
        if n == 0:
            # read everything in chronological order (oldest file first)
            all_entries: list[AuditEntry] = []
            for f in reversed(files):
                all_entries.extend(_read_file(f))
            return all_entries

        # Collect from newest file backwards until we have enough
        chunks: list[list[AuditEntry]] = []
        total = 0
        for f in files:  # newest first
            chunk = _read_file(f)
            if chunk:
                chunks.append(chunk)
                total += len(chunk)
            if total >= n:
                break

        # Flatten in chronological order (oldest chunk last in chunks list)
        merged: list[AuditEntry] = []
        for chunk in reversed(chunks):
            merged.extend(chunk)
        return merged[-n:]

    def filter(
        self,
        decision: str | None = None,
        since: datetime | None = None,
    ) -> list[AuditEntry]:
        entries = self.tail(n=0)
        if decision:
            entries = [e for e in entries if e.decision == decision.upper()]
        if since:
            cutoff = since.replace(tzinfo=UTC) if since.tzinfo is None else since
            entries = [e for e in entries if datetime.fromisoformat(e.timestamp) >= cutoff]
        return entries

    # ------------------------------------------------------------------
    # Rotation helpers
    # ------------------------------------------------------------------

    def _should_rotate(self) -> bool:
        return (
            self._max_bytes > 0
            and self._path.exists()
            and self._path.stat().st_size >= self._max_bytes
        )

    def _rotate(self) -> None:
        """Shift existing backups and rename the current log to .1."""
        # Remove the oldest backup that would overflow backup_count
        oldest = Path(f"{self._path}.{self._backup_count}")
        if oldest.exists():
            oldest.unlink()
        # Shift: .N-1 → .N, …, .1 → .2
        for i in range(self._backup_count - 1, 0, -1):
            src = Path(f"{self._path}.{i}")
            if src.exists():
                src.replace(Path(f"{self._path}.{i + 1}"))
        # Current log → .1
        self._path.replace(Path(f"{self._path}.1"))

    def _all_log_files(self) -> list[Path]:
        """Return existing log files from newest to oldest."""
        files = [self._path]
        for i in range(1, self._backup_count + 1):
            p = Path(f"{self._path}.{i}")
            if p.exists():
                files.append(p)
        return files


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _read_file(path: Path) -> list[AuditEntry]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [_parse(line) for line in lines if line.strip()]


def _parse(line: str) -> AuditEntry:
    d = json.loads(line)
    # key_id and matched_file were added after initial release; default for older log lines
    d.setdefault("key_id", "")
    d.setdefault("matched_file", "")
    return AuditEntry(**d)
