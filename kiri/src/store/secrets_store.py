from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from src.store.atomic_write import atomic_write_lines


class PathTraversalError(Exception):
    pass


class ProtectionStrategy(StrEnum):
    BLOCK = "block"
    REDACT = "redact"


_STRATEGY_RE = re.compile(r"\[strategy=(\w+)\]")


def _parse_strategy(line: str) -> ProtectionStrategy:
    """Extract [strategy=...] from *line*, defaulting to BLOCK."""
    m = _STRATEGY_RE.search(line)
    if m:
        try:
            return ProtectionStrategy(m.group(1))
        except ValueError:
            pass
    return ProtectionStrategy.BLOCK


# ---------------------------------------------------------------------------
# Public dataclasses returned by the read API
# ---------------------------------------------------------------------------


@dataclass
class SubFileEntry:
    """A single function/class within a file to protect."""
    path: Path
    symbol: str


@dataclass
class InlineBlock:
    """A named block of content defined directly in the secrets file."""
    name: str
    content: str


@dataclass
class ValuedSymbol:
    """A @symbol entry that also carries a numeric value."""
    name: str
    value: float


# ---------------------------------------------------------------------------
# SecretsStore
# ---------------------------------------------------------------------------


@dataclass
class SecretsStore:
    secrets_path: Path
    workspace: Path

    # ------------------------------------------------------------------
    # Read API — paths
    # ------------------------------------------------------------------

    def list_paths(self) -> list[Path]:
        return [self._validate_path(self.workspace / p) for p in self._parse_path_entries()]

    # ------------------------------------------------------------------
    # Read API — symbols
    # ------------------------------------------------------------------

    def list_symbols(self) -> list[str]:
        """All @symbol entries (plain and valued)."""
        return self._parse_symbol_entries()

    def list_valued_symbols(self) -> list[ValuedSymbol]:
        """@symbol entries that carry an explicit numeric value."""
        results: list[ValuedSymbol] = []
        for line in self._read_lines():
            s = line.strip()
            if not s.startswith("@symbol "):
                continue
            rest = s.removeprefix("@symbol ").strip()
            if "=" in rest:
                name, _, raw_val = rest.partition("=")
                try:
                    results.append(ValuedSymbol(name=name.strip(), value=float(raw_val.strip())))
                except ValueError:
                    pass
        return results

    # ------------------------------------------------------------------
    # Read API — sub-file entries
    # ------------------------------------------------------------------

    def list_subfile_entries(self) -> list[SubFileEntry]:
        results: list[SubFileEntry] = []
        for line in self._non_inline_lines():
            s = line.strip()
            if not s or s.startswith("#") or s.startswith("@"):
                continue
            if "::" in s:
                raw_path, _, symbol = s.partition("::")
                try:
                    resolved = self._validate_path(self.workspace / raw_path.strip())
                    results.append(SubFileEntry(path=resolved, symbol=symbol.strip()))
                except PathTraversalError:
                    pass
        return results

    # ------------------------------------------------------------------
    # Read API — inline blocks
    # ------------------------------------------------------------------

    def list_inline_blocks(self) -> list[InlineBlock]:
        return self._scan_sections()[1]

    # ------------------------------------------------------------------
    # Strategy lookup
    # ------------------------------------------------------------------

    def get_strategy(self, path: Path) -> ProtectionStrategy:
        """Return the protection strategy for a file (default: BLOCK)."""
        try:
            relative = self._to_relative(path)
        except Exception:
            return ProtectionStrategy.BLOCK
        return self.get_strategy_for_source(relative)

    def get_strategy_for_source(self, source_key: str) -> ProtectionStrategy:
        """Return the protection strategy for any source key.

        Accepted key forms:
          - ``"src/scorer.py"``          — full-file path (relative, forward slashes)
          - ``"src/scorer.py::_fn"``     — sub-file entry
          - ``"@inline:my_algo"``        — inline block (colon, not double-colon)
        """
        if source_key.startswith("@inline:"):
            return self._strategy_for_inline(source_key[len("@inline:"):])
        if "::" in source_key:
            return self._strategy_for_subfile(source_key)
        return self._strategy_for_path(source_key)

    # ------------------------------------------------------------------
    # Strategy helpers
    # ------------------------------------------------------------------

    def _strategy_for_path(self, relative: str) -> ProtectionStrategy:
        for line in self._non_inline_lines():
            s = line.strip()
            if not s or s.startswith("#") or s.startswith("@") or "::" in s:
                continue
            raw_path = _STRATEGY_RE.sub("", s).strip()
            if raw_path.replace("\\", "/") == relative.replace("\\", "/"):
                return _parse_strategy(s)
        return ProtectionStrategy.BLOCK

    def _strategy_for_subfile(self, source_key: str) -> ProtectionStrategy:
        """source_key is ``relative_path::symbol``."""
        for line in self._non_inline_lines():
            s = line.strip()
            if not s or s.startswith("#") or s.startswith("@") or "::" not in s:
                continue
            raw_entry = _STRATEGY_RE.sub("", s).strip()
            if raw_entry.replace("\\", "/") == source_key.replace("\\", "/"):
                return _parse_strategy(s)
        return ProtectionStrategy.BLOCK

    def _strategy_for_inline(self, name: str) -> ProtectionStrategy:
        """Parse strategy from the @inline header line."""
        for line in self._read_lines():
            s = line.strip()
            if not s.startswith("@inline"):
                continue
            block_name = _STRATEGY_RE.sub("", s.removeprefix("@inline")).strip() or "block_?"
            if block_name == name:
                return _parse_strategy(s)
        return ProtectionStrategy.BLOCK

    # ------------------------------------------------------------------
    # Write API — paths
    # ------------------------------------------------------------------

    def add_path(self, path: Path) -> None:
        self._validate_path(path)
        relative = self._to_relative(path)
        lines = self._read_lines()
        existing = {
            line.strip() for line in lines
            if line.strip() and not line.startswith(("#", "@")) and "::" not in line.strip()
        }
        if relative not in existing:
            atomic_write_lines(self.secrets_path, lines + [relative + "\n"])

    def remove_path(self, path: Path) -> None:
        relative = self._to_relative(path)
        lines = self._read_lines()
        filtered = [line for line in lines if line.strip() != relative]
        if len(filtered) != len(lines):
            atomic_write_lines(self.secrets_path, filtered)

    # ------------------------------------------------------------------
    # Write API — symbols
    # ------------------------------------------------------------------

    def add_symbol(self, symbol: str) -> None:
        entry = f"@symbol {symbol}"
        lines = self._read_lines()
        if entry not in {line.strip() for line in lines}:
            atomic_write_lines(self.secrets_path, lines + [entry + "\n"])

    def remove_symbol(self, symbol: str) -> None:
        entry = f"@symbol {symbol}"
        lines = self._read_lines()
        filtered = [line for line in lines if line.strip() != entry]
        if len(filtered) != len(lines):
            atomic_write_lines(self.secrets_path, filtered)

    def add_valued_symbol(self, name: str, value: float) -> None:
        entry = f"@symbol {name} = {value}"
        lines = self._read_lines()
        if entry not in {line.strip() for line in lines}:
            atomic_write_lines(self.secrets_path, lines + [entry + "\n"])

    def remove_valued_symbol(self, name: str) -> None:
        lines = self._read_lines()
        filtered = [
            line for line in lines
            if not (line.strip().startswith(f"@symbol {name}") and "=" in line)
        ]
        if len(filtered) != len(lines):
            atomic_write_lines(self.secrets_path, filtered)

    # ------------------------------------------------------------------
    # Write API — sub-file entries
    # ------------------------------------------------------------------

    def add_subfile(self, path: Path, symbol: str) -> None:
        self._validate_path(path)
        relative = self._to_relative(path)
        entry = f"{relative}::{symbol}"
        lines = self._read_lines()
        if entry not in {line.strip() for line in lines}:
            atomic_write_lines(self.secrets_path, lines + [entry + "\n"])

    def remove_subfile(self, path: Path, symbol: str) -> None:
        try:
            relative = self._to_relative(path)
        except Exception:
            return
        entry = f"{relative}::{symbol}"
        lines = self._read_lines()
        filtered = [line for line in lines if line.strip() != entry]
        if len(filtered) != len(lines):
            atomic_write_lines(self.secrets_path, filtered)

    # ------------------------------------------------------------------
    # Write API — inline blocks
    # ------------------------------------------------------------------

    def add_inline_block(self, name: str, content: str) -> None:
        if any(b.name == name for b in self.list_inline_blocks()):
            return
        lines = self._read_lines()
        block_lines: list[str] = [f"@inline {name}\n"]
        for line in content.splitlines(keepends=True):
            block_lines.append(line if line.endswith("\n") else line + "\n")
        block_lines.append("@end\n")
        atomic_write_lines(self.secrets_path, lines + block_lines)

    def remove_inline_block(self, name: str) -> None:
        lines = self._read_lines()
        result: list[str] = []
        i = 0
        while i < len(lines):
            s = lines[i].strip()
            if s == f"@inline {name}":
                i += 1
                while i < len(lines) and lines[i].strip() != "@end":
                    i += 1
                # skip @end itself
            else:
                result.append(lines[i])
            i += 1
        if len(result) != len(lines):
            atomic_write_lines(self.secrets_path, result)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_lines(self) -> list[str]:
        if not self.secrets_path.exists():
            return []
        return self.secrets_path.read_text(encoding="utf-8").splitlines(keepends=True)

    def _scan_sections(self) -> tuple[list[str], list[InlineBlock]]:
        """Single-pass parse: split lines into outside-block lines and InlineBlock objects.

        Lines that are part of an @inline...@end block — including the @inline
        header and the @end marker — are excluded from *outside*.
        """
        outside: list[str] = []
        blocks: list[InlineBlock] = []
        lines = self._read_lines()
        i = 0
        while i < len(lines):
            s = lines[i].strip()
            if s.startswith("@inline"):
                block_name = _STRATEGY_RE.sub("", s.removeprefix("@inline")).strip() or f"block_{i}"
                i += 1
                body: list[str] = []
                while i < len(lines) and lines[i].strip() != "@end":
                    body.append(lines[i])
                    i += 1
                # i points at @end (or past end if block is unclosed); skip it
                blocks.append(InlineBlock(name=block_name, content="".join(body)))
            else:
                outside.append(lines[i])
            i += 1
        return outside, blocks

    def _non_inline_lines(self) -> list[str]:
        return self._scan_sections()[0]

    def _parse_path_entries(self) -> list[str]:
        """Full-file path entries only.

        Excludes: :: sub-file entries, @-directives, and entries inside @inline blocks.
        """
        results: list[str] = []
        for line in self._non_inline_lines():
            s = line.strip()
            if not s or s.startswith("#") or s.startswith("@") or "::" in s:
                continue
            results.append(_STRATEGY_RE.sub("", s).strip())
        return results

    def _parse_symbol_entries(self) -> list[str]:
        """All @symbol entries — both plain and valued (skips @inline body)."""
        results: list[str] = []
        for line in self._non_inline_lines():
            s = line.strip()
            if not s.startswith("@symbol "):
                continue
            name = s.removeprefix("@symbol ").strip().partition("=")[0].strip()
            if name:
                results.append(name)
        return results

    def _validate_path(self, path: Path) -> Path:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        workspace = self.workspace.resolve()
        if not resolved.is_relative_to(workspace):
            raise PathTraversalError(
                f"path '{path}' is outside workspace '{workspace}'"
            )
        return resolved

    def _to_relative(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.workspace.resolve()))
        except ValueError:
            return str(path)
