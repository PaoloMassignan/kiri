from __future__ import annotations

from pathlib import Path

from src.config.settings import Settings
from src.filter.pipeline import Decision, FilterResult

# --- fakes --------------------------------------------------------------------


class FakePipeline:
    def __init__(self, decision: Decision, reason: str, similarity: float = 0.5) -> None:
        self._result = FilterResult(
            decision=decision,
            reason=reason,
            top_similarity=similarity,
            matched_symbols=[],
        )

    def run(self, prompt: str) -> FilterResult:
        return self._result


# --- inspect output -----------------------------------------------------------


def test_inspect_returns_string(tmp_path: Path) -> None:
    from src.cli.commands.inspect import run

    pipeline = FakePipeline(Decision.PASS, "below threshold", 0.3)

    result = run("explain quicksort", Settings(workspace=tmp_path), pipeline=pipeline)  # type: ignore[arg-type]

    assert isinstance(result, str)


def test_inspect_pass_shows_pass_decision(tmp_path: Path) -> None:
    from src.cli.commands.inspect import run

    pipeline = FakePipeline(Decision.PASS, "below threshold", 0.3)

    result = run("explain quicksort", Settings(workspace=tmp_path), pipeline=pipeline)  # type: ignore[arg-type]

    assert "pass" in result.lower()


def test_inspect_block_shows_block_decision(tmp_path: Path) -> None:
    from src.cli.commands.inspect import run

    pipeline = FakePipeline(Decision.BLOCK, "symbol match: RiskScorer", 0.85)

    result = run("show RiskScorer", Settings(workspace=tmp_path), pipeline=pipeline)  # type: ignore[arg-type]

    assert "block" in result.lower()


def test_inspect_shows_reason(tmp_path: Path) -> None:
    from src.cli.commands.inspect import run

    pipeline = FakePipeline(Decision.BLOCK, "symbol match: RiskScorer", 0.85)

    result = run("show RiskScorer", Settings(workspace=tmp_path), pipeline=pipeline)  # type: ignore[arg-type]

    assert "RiskScorer" in result


def test_inspect_shows_similarity_score(tmp_path: Path) -> None:
    from src.cli.commands.inspect import run

    pipeline = FakePipeline(Decision.PASS, "below threshold", 0.42)

    result = run("some prompt", Settings(workspace=tmp_path), pipeline=pipeline)  # type: ignore[arg-type]

    assert "0.42" in result or "42" in result


def test_inspect_passes_prompt_to_pipeline(tmp_path: Path) -> None:
    from src.cli.commands.inspect import run

    captured: list[str] = []

    class CapturingPipeline:
        def run(self, prompt: str) -> FilterResult:
            captured.append(prompt)
            return FilterResult(
                decision=Decision.PASS, reason="ok", top_similarity=0.0
            )

    run("my secret prompt", Settings(workspace=tmp_path), pipeline=CapturingPipeline())  # type: ignore[arg-type]

    assert captured == ["my secret prompt"]
