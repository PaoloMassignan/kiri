from __future__ import annotations

import re

# --- fakes --------------------------------------------------------------------


class FakeSymbolStore:
    def __init__(self, symbols: list[str]) -> None:
        self._symbols = symbols

    def scan_with_source(self, prompt: str) -> list[tuple[str, str]]:
        return [
            (s, "fake.py")
            for s in self._symbols
            if re.search(rf"\b{re.escape(s)}\b", prompt)
        ]


# --- construction -------------------------------------------------------------


def test_l2_constructs_without_error() -> None:
    from src.filter.l2_symbols import L2Filter

    l2 = L2Filter(symbol_store=FakeSymbolStore([]))  # type: ignore[arg-type]

    assert l2 is not None


# --- no match -----------------------------------------------------------------


def test_l2_no_symbols_returns_empty_matched() -> None:
    from src.filter.l2_symbols import L2Filter

    l2 = L2Filter(symbol_store=FakeSymbolStore([]))  # type: ignore[arg-type]

    result = l2.check("how does this work?")

    assert result.matched == []


def test_l2_prompt_with_no_known_symbols_returns_empty() -> None:
    from src.filter.l2_symbols import L2Filter

    l2 = L2Filter(symbol_store=FakeSymbolStore(["RiskScorer"]))  # type: ignore[arg-type]

    result = l2.check("how does the auth module work?")

    assert result.matched == []


# --- match --------------------------------------------------------------------


def test_l2_returns_matched_symbol() -> None:
    from src.filter.l2_symbols import L2Filter

    l2 = L2Filter(symbol_store=FakeSymbolStore(["RiskScorer"]))  # type: ignore[arg-type]

    result = l2.check("show me how RiskScorer is implemented")

    assert "RiskScorer" in result.matched


def test_l2_returns_all_matched_symbols() -> None:
    from src.filter.l2_symbols import L2Filter

    l2 = L2Filter(  # type: ignore[arg-type]
        symbol_store=FakeSymbolStore(["RiskScorer", "sliding_window", "MAX_RETRIES"])
    )

    result = l2.check("RiskScorer uses sliding_window internally")

    assert "RiskScorer" in result.matched
    assert "sliding_window" in result.matched
    assert "MAX_RETRIES" not in result.matched


def test_l2_returns_list_of_strings() -> None:
    from src.filter.l2_symbols import L2Filter

    l2 = L2Filter(symbol_store=FakeSymbolStore(["Foo"]))  # type: ignore[arg-type]

    result = l2.check("Foo is used here")

    assert isinstance(result.matched, list)
    assert all(isinstance(s, str) for s in result.matched)


# --- whole-word matching ------------------------------------------------------


def test_l2_does_not_match_partial_symbol() -> None:
    from src.filter.l2_symbols import L2Filter

    l2 = L2Filter(symbol_store=FakeSymbolStore(["Risk"]))  # type: ignore[arg-type]

    result = l2.check("show me RiskScorer")

    assert "Risk" not in result.matched


def test_l2_matches_exact_word_boundary() -> None:
    from src.filter.l2_symbols import L2Filter

    l2 = L2Filter(symbol_store=FakeSymbolStore(["Risk"]))  # type: ignore[arg-type]

    result = l2.check("the Risk level is high")

    assert "Risk" in result.matched


# --- delegation to store ------------------------------------------------------


def test_l2_dekiris_to_symbol_store_scan() -> None:
    from src.filter.l2_symbols import L2Filter

    calls: list[str] = []

    class TrackingStore:
        def scan_with_source(self, prompt: str) -> list[tuple[str, str]]:
            calls.append(prompt)
            return []

    prompt = "explain this code"
    l2 = L2Filter(symbol_store=TrackingStore())  # type: ignore[arg-type]
    l2.check(prompt)

    assert calls == [prompt]
