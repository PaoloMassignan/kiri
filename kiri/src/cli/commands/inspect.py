from __future__ import annotations

from typing import TYPE_CHECKING

from src.config.settings import Settings
from src.filter.pipeline import Decision, FilterPipeline

if TYPE_CHECKING:
    from src.redaction.engine import RedactionEngine


def run(
    prompt: str,
    settings: Settings,
    *,
    pipeline: FilterPipeline | None = None,
    show_redacted: bool = False,
) -> str:
    if pipeline is None:
        pipeline = _build_pipeline(settings)

    result = pipeline.run(prompt)

    lines = [
        f"Decision   : {result.decision.value.upper()}",
        f"Reason     : {result.reason}",
        f"Similarity : {result.top_similarity:.4f}",
    ]
    if result.matched_symbols:
        lines.append(f"Symbols    : {', '.join(result.matched_symbols)}")

    if show_redacted and result.decision == Decision.REDACT:
        engine = _build_redaction_engine(settings)
        redaction = engine.redact(prompt)
        lines.append("")
        lines.append("--- Prompt as forwarded to LLM ---")
        msg = (
            redaction.redacted_prompt
            if redaction.was_redacted
            else "(no changes — symbol matched but body not found in prompt)"
        )
        lines.append(msg)

    return "\n".join(lines)


def _build_pipeline(settings: Settings) -> FilterPipeline:
    from src.cli.factory import make_secrets_store, make_symbol_store, make_vector_store
    from src.filter.l1_similarity import L1Filter
    from src.filter.l2_symbols import L2Filter
    from src.filter.l3_classifier import L3Filter
    from src.indexer.embedder import Embedder

    vs = make_vector_store(settings)
    ss = make_symbol_store(settings)
    secrets_store = make_secrets_store(settings)
    embedder = Embedder(settings=settings)

    l1 = L1Filter(vector_store=vs, embedder=embedder)
    l2 = L2Filter(symbol_store=ss)
    l3 = L3Filter(settings=settings)

    return FilterPipeline(settings=settings, l1=l1, l2=l2, l3=l3, secrets_store=secrets_store)


def _build_redaction_engine(settings: Settings) -> RedactionEngine:
    from src.cli.factory import make_symbol_store
    from src.redaction.engine import RedactionEngine
    from src.store.summary_store import SummaryStore

    ss = make_symbol_store(settings)
    summary_store = SummaryStore(index_dir=settings.workspace / ".kiri" / "index")
    return RedactionEngine(summary_store=summary_store, symbol_store=ss)
