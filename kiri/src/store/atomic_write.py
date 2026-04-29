"""Atomic file-write helpers shared across store modules.

Both write functions follow the same sequence:
  1. Create a temp file in the same directory (guarantees same filesystem).
  2. Set permissions to 0o600 before writing (no-op on Windows).
  3. Write content.
  4. Rename temp → target (atomic on POSIX; best-effort on Windows).

On failure the temp file is removed and the exception re-raised, leaving the
original file untouched.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def atomic_write_json(path: Path, data: object) -> None:
    """Serialize *data* as JSON and write to *path* atomically."""
    _write(path, lambda f: json.dump(data, f, indent=2, ensure_ascii=False))


def atomic_write_lines(path: Path, lines: list[str]) -> None:
    """Write *lines* to *path* atomically."""
    _write(path, lambda f: f.writelines(lines))


def _write(path: Path, write_fn: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        try:
            Path(tmp).chmod(0o600)
        except (NotImplementedError, OSError):
            pass  # Windows — chmod not supported
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            write_fn(f)  # type: ignore[operator]
        Path(tmp).replace(path)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise
