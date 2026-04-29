from __future__ import annotations

from dataclasses import dataclass, field

from src.store.symbol_store import SymbolStore


@dataclass
class L2Result:
    matched: list[str] = field(default_factory=list)
    matched_with_source: list[tuple[str, str]] = field(default_factory=list)


class L2Filter:
    def __init__(self, symbol_store: SymbolStore) -> None:
        self._ss = symbol_store

    def check(self, prompt: str) -> L2Result:
        with_source = self._ss.scan_with_source(prompt)
        return L2Result(
            matched=[sym for sym, _ in with_source],
            matched_with_source=with_source,
        )
