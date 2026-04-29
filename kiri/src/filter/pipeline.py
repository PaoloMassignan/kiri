from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from src.config.settings import Settings
from src.filter.l1_similarity import L1Filter
from src.filter.l2_symbols import L2Filter
from src.filter.l3_classifier import L3Filter
from src.store.secrets_store import SecretsStore


class Decision(StrEnum):
    PASS = "pass"  # noqa: S105
    BLOCK = "block"
    REDACT = "redact"


@dataclass
class FilterResult:
    decision: Decision
    reason: str
    top_similarity: float
    matched_symbols: list[str] = field(default_factory=list)
    matched_file: str = ""  # source file that triggered L1 similarity


class FilterPipeline:
    def __init__(
        self,
        settings: Settings,
        l1: L1Filter,
        l2: L2Filter,
        l3: L3Filter,
        secrets_store: SecretsStore,
    ) -> None:
        self._settings = settings
        self._l1 = l1
        self._l2 = l2
        self._l3 = l3
        self._secrets = secrets_store

    def run(self, prompt: str) -> FilterResult:
        # L2 always runs first — explicit @symbols are protected even with
        # an empty vector store (before the first indexing cycle completes)
        l2 = self._l2.check(prompt)
        if l2.matched:
            symbols_str = ", ".join(l2.matched)
            return FilterResult(
                decision=Decision.REDACT,
                reason=f"symbol match: {symbols_str}",
                top_similarity=0.0,
                matched_symbols=l2.matched,
            )

        l1 = self._l1.check(prompt)
        score = l1.top_score

        if score >= self._settings.hard_block_threshold:
            return FilterResult(
                decision=Decision.REDACT,
                reason=f"similarity hard block (score={score:.3f})",
                top_similarity=score,
                matched_file=l1.top_source_file,
            )

        if score < self._settings.similarity_threshold:
            return FilterResult(
                decision=Decision.PASS,
                reason=f"below threshold (score={score:.3f})",
                top_similarity=score,
                matched_file=l1.top_source_file,
            )

        # grace zone — L3 decides; BLOCK only on explicit extraction intent
        l3 = self._l3.check(prompt)
        if l3.is_leak:
            return FilterResult(
                decision=Decision.BLOCK,
                reason="classifier: leak detected",
                top_similarity=score,
                matched_file=l1.top_source_file,
            )

        return FilterResult(
            decision=Decision.REDACT,
            reason=f"grace zone: redact on suspicion (score={score:.3f})",
            top_similarity=score,
            matched_file=l1.top_source_file,
        )
