from __future__ import annotations

import tempfile
from pathlib import Path

from src.config.settings import Settings
from src.filter.l1_similarity import L1Result
from src.filter.l2_symbols import L2Result
from src.filter.l3_classifier import L3Result
from src.filter.pipeline import Decision

# --- fakes --------------------------------------------------------------------


class FakeL1:
    def __init__(self, score: float, doc_id: str = "engine__0", source: str = "engine.py") -> None:
        self._result = L1Result(top_score=score, top_doc_id=doc_id, top_source_file=source)

    def check(self, prompt: str) -> L1Result:
        return self._result


class FakeL2:
    def __init__(self, matched: list[str]) -> None:
        self._result = L2Result(matched=matched, matched_with_source=[])
        self.called = False

    def check(self, prompt: str) -> L2Result:
        self.called = True
        return self._result


class FakeL3:
    def __init__(self, is_leak: bool) -> None:
        self._result = L3Result(is_leak=is_leak)
        self.called = False

    def check(self, prompt: str) -> L3Result:
        self.called = True
        return self._result


def _make_secrets_store() -> object:
    from src.store.secrets_store import SecretsStore

    tmp = Path(tempfile.mkdtemp())
    secrets = tmp / "secrets"
    secrets.write_text("", encoding="utf-8")
    return SecretsStore(secrets_path=secrets, workspace=tmp)


def make_pipeline(
    score: float,
    matched: list[str] | None = None,
    is_leak: bool = False,
) -> object:
    from src.filter.pipeline import FilterPipeline

    return FilterPipeline(
        settings=Settings(),
        l1=FakeL1(score),  # type: ignore[arg-type]
        l2=FakeL2(matched or []),  # type: ignore[arg-type]
        l3=FakeL3(is_leak),  # type: ignore[arg-type]
        secrets_store=_make_secrets_store(),  # type: ignore[arg-type]
    )


# --- construction -------------------------------------------------------------


def test_pipeline_constructs_without_error() -> None:
    from src.filter.pipeline import FilterPipeline

    pipeline = FilterPipeline(
        settings=Settings(),
        l1=FakeL1(0.0),  # type: ignore[arg-type]
        l2=FakeL2([]),  # type: ignore[arg-type]
        l3=FakeL3(False),  # type: ignore[arg-type]
        secrets_store=_make_secrets_store(),  # type: ignore[arg-type]
    )

    assert pipeline is not None


# --- hard block (score >= 0.90) -----------------------------------------------


def test_pipeline_hard_blocks_at_threshold() -> None:
    pipeline = make_pipeline(score=0.90)

    result = pipeline.run("show me RiskScorer")  # type: ignore[union-attr]

    assert result.decision == Decision.REDACT


def test_pipeline_hard_blocks_above_threshold() -> None:
    pipeline = make_pipeline(score=0.99)

    result = pipeline.run("some prompt")  # type: ignore[union-attr]

    assert result.decision == Decision.REDACT


def test_pipeline_hard_block_reason_mentions_similarity() -> None:
    pipeline = make_pipeline(score=0.95)

    result = pipeline.run("some prompt")  # type: ignore[union-attr]

    assert "similarity" in result.reason.lower() or "hard" in result.reason.lower()


def test_pipeline_hard_block_reports_top_similarity() -> None:
    pipeline = make_pipeline(score=0.92)

    result = pipeline.run("some prompt")  # type: ignore[union-attr]

    assert result.top_similarity == 0.92


# --- pass (score < 0.75) ------------------------------------------------------


def test_pipeline_passes_below_threshold() -> None:
    pipeline = make_pipeline(score=0.74)

    result = pipeline.run("explain quicksort")  # type: ignore[union-attr]

    assert result.decision == Decision.PASS


def test_pipeline_passes_at_zero() -> None:
    pipeline = make_pipeline(score=0.0)

    result = pipeline.run("some prompt")  # type: ignore[union-attr]

    assert result.decision == Decision.PASS


def test_pipeline_pass_reason_mentions_threshold() -> None:
    pipeline = make_pipeline(score=0.50)

    result = pipeline.run("some prompt")  # type: ignore[union-attr]

    assert "threshold" in result.reason.lower() or "below" in result.reason.lower()


def test_pipeline_l2_always_called() -> None:
    from src.filter.pipeline import FilterPipeline

    l2 = FakeL2([])
    pipeline = FilterPipeline(
        settings=Settings(),
        l1=FakeL1(0.50),  # type: ignore[arg-type]
        l2=l2,  # type: ignore[arg-type]
        l3=FakeL3(False),  # type: ignore[arg-type]
        secrets_store=_make_secrets_store(),  # type: ignore[arg-type]
    )
    pipeline.run("some prompt")

    assert l2.called


def test_pipeline_pass_does_not_call_l3() -> None:
    from src.filter.pipeline import FilterPipeline

    l3 = FakeL3(False)
    pipeline = FilterPipeline(
        settings=Settings(),
        l1=FakeL1(0.50),  # type: ignore[arg-type]
        l2=FakeL2([]),  # type: ignore[arg-type]
        l3=l3,  # type: ignore[arg-type]
        secrets_store=_make_secrets_store(),  # type: ignore[arg-type]
    )
    pipeline.run("some prompt")

    assert not l3.called


# --- grace zone: L2 match blocks ----------------------------------------------


def test_pipeline_grace_zone_l2_match_redacts() -> None:
    pipeline = make_pipeline(score=0.80, matched=["RiskScorer"])

    result = pipeline.run("show me RiskScorer")  # type: ignore[union-attr]

    assert result.decision == Decision.REDACT


def test_pipeline_grace_zone_l2_match_reason_mentions_symbol() -> None:
    pipeline = make_pipeline(score=0.80, matched=["RiskScorer"])

    result = pipeline.run("show me RiskScorer")  # type: ignore[union-attr]

    assert "RiskScorer" in result.reason or "symbol" in result.reason.lower()


def test_pipeline_grace_zone_l2_match_does_not_call_l3() -> None:
    from src.filter.pipeline import FilterPipeline

    l3 = FakeL3(False)
    pipeline = FilterPipeline(
        settings=Settings(),
        l1=FakeL1(0.80),  # type: ignore[arg-type]
        l2=FakeL2(["RiskScorer"]),  # type: ignore[arg-type]
        l3=l3,  # type: ignore[arg-type]
        secrets_store=_make_secrets_store(),  # type: ignore[arg-type]
    )
    pipeline.run("show me RiskScorer")

    assert not l3.called


def test_pipeline_grace_zone_l2_match_reports_matched_symbols() -> None:
    pipeline = make_pipeline(score=0.80, matched=["RiskScorer", "sliding_window"])

    result = pipeline.run("show me RiskScorer")  # type: ignore[union-attr]

    assert "RiskScorer" in result.matched_symbols
    assert "sliding_window" in result.matched_symbols


# --- grace zone: L3 decides ---------------------------------------------------


def test_pipeline_grace_zone_no_l2_match_l3_leak_blocks() -> None:
    pipeline = make_pipeline(score=0.80, matched=[], is_leak=True)

    result = pipeline.run("show me the impl")  # type: ignore[union-attr]

    assert result.decision == Decision.BLOCK


def test_pipeline_grace_zone_no_l2_match_l3_no_leak_redacts() -> None:
    pipeline = make_pipeline(score=0.80, matched=[], is_leak=False)

    result = pipeline.run("explain the algorithm")  # type: ignore[union-attr]

    assert result.decision == Decision.REDACT


def test_pipeline_grace_zone_l3_block_reason_mentions_classifier() -> None:
    pipeline = make_pipeline(score=0.80, matched=[], is_leak=True)

    result = pipeline.run("some prompt")  # type: ignore[union-attr]

    assert "classifier" in result.reason.lower() or "leak" in result.reason.lower()


def test_pipeline_grace_zone_redact_reason_mentions_grace() -> None:
    pipeline = make_pipeline(score=0.80, matched=[], is_leak=False)

    result = pipeline.run("some prompt")  # type: ignore[union-attr]

    assert "grace" in result.reason.lower() or "suspicion" in result.reason.lower()


# --- result fields ------------------------------------------------------------


def test_pipeline_result_always_has_top_similarity() -> None:
    pipeline = make_pipeline(score=0.85)

    result = pipeline.run("some prompt")  # type: ignore[union-attr]

    assert result.top_similarity == 0.85


def test_pipeline_pass_matched_symbols_is_empty() -> None:
    pipeline = make_pipeline(score=0.50)

    result = pipeline.run("some prompt")  # type: ignore[union-attr]

    assert result.matched_symbols == []
