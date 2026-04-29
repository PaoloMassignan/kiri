from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from src.store.atomic_write import atomic_write_json

_EXPLICIT_KEY = "@explicit"
_NUMBERS_KEY = "@numbers"

# Matches numeric literals in a prompt: optional sign, integer or decimal,
# optional scientific notation, optional trailing % sign.
_NUMBER_RE = re.compile(
    r"(?<!\w)([+-]?\s*(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?\s*%?)(?!\w)"
)

_REL_TOL = 0.01   # 1% relative tolerance
_SIG_FIGS_RE = re.compile(r"^[+-]?\s*0*\.?0*([1-9][\d]*\.?[\d]*)$")


class SymbolStore:
    def __init__(self, index_dir: Path) -> None:
        self._path = index_dir / "symbols.json"
        self._index_dir = index_dir

    # ------------------------------------------------------------------
    # String symbols
    # ------------------------------------------------------------------

    def add(self, source_file: str, symbols: list[str]) -> None:
        data = self._load()
        data[source_file] = symbols
        self._save(data)

    def add_explicit(self, symbols: list[str]) -> None:
        data = self._load()
        existing = set(data.get(_EXPLICIT_KEY, []))
        data[_EXPLICIT_KEY] = list(existing | set(symbols))
        self._save(data)

    def all_symbols(self) -> set[str]:
        data = self._load()
        return {
            symbol
            for key, symbols in data.items()
            if key != _NUMBERS_KEY
            for symbol in symbols
        }

    def symbols_for(self, source_file: str) -> list[str]:
        result = self._load().get(source_file, [])
        return result if isinstance(result, list) else []

    # ------------------------------------------------------------------
    # Numeric constants
    # ------------------------------------------------------------------

    def add_numbers(self, source_file: str, values: list[tuple[float, int]]) -> None:
        """Store numeric constants as (value, sig_figs) pairs."""
        if not values:
            return
        data = self._load()
        nums: dict[str, list[list[Any]]] = data.get(_NUMBERS_KEY, {})
        nums[source_file] = [[v, sf] for v, sf in values]
        data[_NUMBERS_KEY] = nums
        self._save(data)

    def all_numbers(self) -> list[tuple[float, int]]:
        nums: dict[str, list[list[Any]]] = self._load().get(_NUMBERS_KEY, {})
        result: list[tuple[float, int]] = []
        for pairs in nums.values():
            for pair in pairs:
                result.append((float(pair[0]), int(pair[1])))
        return result

    def scan_numbers(self, prompt: str) -> list[float]:
        """
        Return protected numeric constants found in the prompt.

        A match requires:
        1. Values within 1% relative tolerance.
        2. The number as written in the prompt has at least as many significant
           figures as the protected constant — prevents ``30%`` (2 sig figs)
           from matching ``0.298`` (3 sig figs).
        """
        protected = self.all_numbers()
        if not protected:
            return []
        prompt_numbers = _parse_prompt_numbers(prompt)
        if not prompt_numbers:
            return []
        matched: list[float] = []
        for prot_val, prot_sf in protected:
            for pn_val, pn_sf in prompt_numbers:
                if pn_sf >= prot_sf and _close(pn_val, prot_val):
                    matched.append(prot_val)
                    break
        return list(dict.fromkeys(matched))  # deduplicate, preserve order

    # ------------------------------------------------------------------
    # Combined scan (used by L2Filter)
    # ------------------------------------------------------------------

    def scan(self, prompt: str) -> list[str]:
        """Return all matches as symbol name strings (backward compat)."""
        return [sym for sym, _ in self.scan_with_source(prompt)]

    def scan_with_source(self, prompt: str) -> list[tuple[str, str]]:
        """Return (symbol, source_file) for every match in the prompt."""
        data = self._load()
        results: list[tuple[str, str]] = []
        seen: set[str] = set()

        # String symbol matches — preserve source_file per entry
        for source_file, symbols in data.items():
            if source_file == _NUMBERS_KEY:
                continue
            if not isinstance(symbols, list):
                continue
            for sym in symbols:
                if sym in seen:
                    continue
                if re.search(rf"\b{re.escape(sym)}\b", prompt):
                    results.append((sym, source_file))
                    seen.add(sym)

        # Numeric constant matches
        nums: dict[str, list[list[Any]]] = data.get(_NUMBERS_KEY, {})
        prompt_numbers = _parse_prompt_numbers(prompt)
        for source_file, pairs in nums.items():
            for pair in pairs:
                prot_val, prot_sf = float(pair[0]), int(pair[1])
                for pn_val, pn_sf in prompt_numbers:
                    if pn_sf >= prot_sf and _close(pn_val, prot_val):
                        sym_key = str(prot_val)
                        if sym_key not in seen:
                            results.append((sym_key, source_file))
                            seen.add(sym_key)
                        break

        return results

    # ------------------------------------------------------------------
    # Removal
    # ------------------------------------------------------------------

    def remove(self, source_file: str) -> None:
        data = self._load()
        changed = False
        if source_file in data:
            del data[source_file]
            changed = True
        nums: dict[str, list[list[Any]]] = data.get(_NUMBERS_KEY, {})
        if source_file in nums:
            del nums[source_file]
            data[_NUMBERS_KEY] = nums
            changed = True
        if changed:
            self._save(data)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]

    def _save(self, data: dict[str, Any]) -> None:
        atomic_write_json(self._path, data)


def _close(a: float, b: float) -> bool:
    """1% relative tolerance, with absolute fallback for values near zero."""
    return math.isclose(a, b, rel_tol=_REL_TOL, abs_tol=1e-9)


def _count_sig_figs(raw: str) -> int:
    """
    Count significant figures in a numeric string.

    Rules:
    - Leading zeros (before the first nonzero digit) are never significant.
    - Trailing zeros after the decimal point but beyond the last nonzero digit
      are NOT counted — ``0.4632247000000`` and ``0.4632247`` both give 7.
    - Trailing zeros in integers ARE counted — ``44100`` gives 5.
    - The decimal point itself is not a digit.

    Examples:
      "0.3"    -> 1    "0.30"   -> 1    "0.298"       -> 3
      "580"    -> 3    "30"     -> 2    "3.2174"       -> 5
      "1.8831" -> 5    "0.341"  -> 3    "0.4632247000" -> 7
      "1.00"   -> 1    "4.0"    -> 1    "44100"        -> 5
    """
    raw = raw.strip().lstrip("+-").replace(" ", "")
    if raw.endswith("%"):
        raw = raw[:-1]
    has_decimal = "." in raw
    # handle scientific notation: only the mantissa counts
    if "e" in raw.lower():
        raw = raw.lower().split("e")[0]
    # remove decimal point to get a digit-only string
    digits = raw.replace(".", "")
    # strip leading zeros (never significant)
    stripped = digits.lstrip("0")
    # strip trailing zeros only for decimal numbers — in integers they are
    # part of the magnitude (44100 ≠ 441) and must not be discarded
    if has_decimal:
        stripped = stripped.rstrip("0")
    return len(stripped) if stripped else 1


def _parse_prompt_numbers(prompt: str) -> list[tuple[float, int]]:
    """
    Extract all numeric values from a prompt (including percentages).
    Returns (value_as_float, significant_figures) pairs.
    """
    results: list[tuple[float, int]] = []
    for m in _NUMBER_RE.finditer(prompt):
        raw = m.group(1).replace(" ", "")
        is_pct = raw.endswith("%")
        num_str = raw[:-1] if is_pct else raw
        try:
            value = float(num_str)
        except ValueError:
            continue
        if is_pct:
            value /= 100.0
        sf = _count_sig_figs(num_str)
        results.append((value, sf))
    return results
