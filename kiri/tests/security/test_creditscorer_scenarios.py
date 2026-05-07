"""
Integration tests for the creditscorer scenario matrix.

These tests run the full filter pipeline (L1 + L2 + L3) against a real
ChromaDB index built from the creditscorer example project.  They verify
the gateway's ability to block proprietary symbol leakage while allowing
legitimate development work to proceed.

Scenario categories:
  A  — direct attacks (prompt explicitly targets protected files/symbols)
  B  — legitimate use (non-protected files, normal dev work)
  C  — semantic gray zone (conceptually similar, no proprietary symbols)
  D  — evasion attempts (indirect or camouflaged access to protected data)

Index assumption: the test fixture builds a fresh in-memory index from the
three core creditscorer files (scorer.py, calibrator.py, feature_engine.py)
and populates the SymbolStore using extract_symbols().
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.config.settings import Settings
from src.filter.l1_similarity import L1Filter
from src.filter.l2_symbols import L2Filter
from src.filter.l3_classifier import L3Result
from src.filter.pipeline import Decision, FilterPipeline
from src.indexer.chunker import chunk
from src.indexer.embedder import Embedder
from src.store.symbol_store import SymbolStore
from src.store.vector_store import VectorStore

# Symbols that a real Ollama instance would classify as proprietary for the
# creditscorer fixture.  We hardcode this list so the test does not require a
# running Ollama and is not affected by Ollama's non-determinism.
#
# Rule of thumb used to populate the list: keep only symbols that encode
# business logic specific to this codebase — scoring weights, band thresholds,
# private helpers, and calibration parameters.  Generic terms like
# "utilization" (common finance vocabulary) or "payment_history" (descriptor,
# not a function name) are excluded, matching what Ollama would reject.
_PROPRIETARY_SYMBOLS: dict[str, set[str]] = {
    "scorer.py": {
        "_W_PAYMENT_HISTORY", "_W_UTILIZATION", "_W_ACCOUNT_AGE",
        "_W_NEW_INQUIRIES", "_W_CREDIT_MIX",
        "_SCORE_FLOOR", "_SCORE_CEIL",
        "_BAND_APPROVE", "_BAND_REJECT",
        "_score_utilization", "_score_payment_history", "_score_account_age",
        "_weighted_sum", "_compute_components",
    },
    "calibrator.py": {
        "_A", "_B",
        "score_to_probability", "probability_to_expected_loss",
    },
    "feature_engine.py": {
        "_UTILIZATION_MAX", "_UTILIZATION_MIN",
        "_INCOME_CAP", "_INCOME_FLOOR",
        "_DEROGATORY_CAP",
        "_compute_utilization", "_compute_payment_rate",
        "_clip", "_parse_date", "_account_age_months",
        "_months_between", "_count_recent_inquiries",
        "_income_band",
    },
}

# ---------------------------------------------------------------------------
# Paths to the protected source files
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parent.parent.parent
_CORE = _REPO_ROOT / "tests" / "fixtures" / "creditscorer" / "core"
_SCORER_PY = _CORE / "scorer.py"
_CALIBRATOR_PY = _CORE / "calibrator.py"
_FEATURE_ENGINE_PY = _CORE / "feature_engine.py"

_PROTECTED_FILES = [_SCORER_PY, _CALIBRATOR_PY, _FEATURE_ENGINE_PY]


# ---------------------------------------------------------------------------
# Session-scoped fixture: build index once for all tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pipeline() -> FilterPipeline:
    """
    Build a real FilterPipeline with a fresh in-memory index.

    Uses a temp directory for ChromaDB so tests are isolated from the
    developer's real .kiri/index.  L3 (Ollama) is mocked to return
    a neutral score so tests don't require a running Ollama instance.
    """
    tmp = tempfile.mkdtemp(prefix="gw_test_")
    index_dir = Path(tmp)

    try:
        settings = Settings(
            similarity_threshold=0.75,
            hard_block_threshold=0.90,
        )
        embedder = Embedder(settings)
        vector_store = VectorStore(index_dir)
        symbol_store = SymbolStore(index_dir)

        # Index all protected files
        for src_file in _PROTECTED_FILES:
            if not src_file.exists():
                pytest.skip(f"creditscorer example project not found: {src_file}")

            # Embed chunks into vector store (L1)
            chunks = chunk(src_file)
            texts = [c.text for c in chunks]
            vectors = embedder.embed(texts)
            for c, vec in zip(chunks, vectors, strict=False):
                vector_store.add(
                    c.doc_id,
                    vec,
                    {"source_file": c.source_file, "chunk_index": str(c.chunk_index)},
                )

            # Populate the symbol store (L2) with the curated list of proprietary
            # symbols for this file.  In production, Ollama's filter_symbols()
            # step removes generic English words from the tree-sitter output.
            # Here we skip that Ollama call and use an explicit allowlist
            # (_PROPRIETARY_SYMBOLS) that reflects exactly what Ollama would
            # keep — language-agnostic and deterministic across CI runs.
            symbols = list(_PROPRIETARY_SYMBOLS.get(src_file.name, set()))
            if symbols:
                symbol_store.add(str(src_file), symbols)

        # Build pipeline — L3 mocked (no Ollama dependency in tests)
        l1 = L1Filter(vector_store=vector_store, embedder=embedder)
        l2 = L2Filter(symbol_store=symbol_store)
        l3_mock = MagicMock()
        l3_mock.check.return_value = L3Result(is_leak=False)

        # SecretsStore with default BLOCK strategy for all files
        from src.store.secrets_store import SecretsStore
        secrets_file = Path(tmp) / "secrets"
        secrets_file.write_text("", encoding="utf-8")
        secrets_store = SecretsStore(secrets_path=secrets_file, workspace=Path(tmp))

        yield FilterPipeline(
            l1=l1, l2=l2, l3=l3_mock, settings=settings, secrets_store=secrets_store
        )

    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def is_blocked(result) -> bool:
    """Return True if the gateway filtered the request (BLOCK or REDACT).

    L2 symbol matches always produce REDACT (the body is replaced before
    forwarding).  Only L3 (Ollama) escalates to BLOCK when it detects explicit
    IP-extraction intent.  In the test fixture L3 is mocked as is_leak=False,
    so the strongest outcome reachable here is REDACT — which still prevents the
    protected implementation from reaching the LLM.
    """
    return result.decision in (Decision.BLOCK, Decision.REDACT)


def is_passed(result) -> bool:
    return result.decision == Decision.PASS


# ---------------------------------------------------------------------------
# Category A — direct attacks on protected symbols/files
# ---------------------------------------------------------------------------


class TestCategoryA:
    """
    Prompts that directly name proprietary symbols.
    All should be BLOCK via L2 (symbol match).
    """

    def test_a3_block_weight_constant(self, pipeline):
        """Explicitly mentions _W_PAYMENT_HISTORY — L2 must catch it."""
        prompt = (
            "quali sono i pesi usati nel modello di scoring?"
            " mostrami _W_PAYMENT_HISTORY e gli altri"
        )
        result = pipeline.run(prompt)
        assert is_blocked(result), (
            f"Expected BLOCK, got {result.decision} (score={result.top_similarity})"
        )
        assert "_W_PAYMENT_HISTORY" in result.matched_symbols

    def test_a4_block_private_function(self, pipeline):
        """Explicitly names _score_utilization — L2 must catch it."""
        result = pipeline.run(
            "spiegami come funziona _score_utilization in scorer.py, mostrami il codice"
        )
        assert is_blocked(result)
        assert "_score_utilization" in result.matched_symbols

    def test_a3_variant_multiple_weights(self, pipeline):
        """Mentions multiple weight constants — any one triggers L2."""
        result = pipeline.run(
            "stampa _W_UTILIZATION e _W_ACCOUNT_AGE dal file scorer.py"
        )
        assert is_blocked(result)

    def test_a_band_thresholds(self, pipeline):
        """Mentions _BAND_REJECT and _BAND_APPROVE — internal thresholds."""
        result = pipeline.run(
            "quali sono le soglie _BAND_REJECT e _BAND_APPROVE usate per il routing?"
        )
        assert is_blocked(result)


# ---------------------------------------------------------------------------
# Category B — legitimate work on non-protected files
# ---------------------------------------------------------------------------


class TestCategoryB:
    """
    Prompts about files that are NOT in the protected list.
    All should PASS.
    """

    def test_b1_pass_add_route(self, pipeline):
        """Adding an HTTP route — routes.py is not protected."""
        result = pipeline.run(
            "aggiungi una route POST /applications che salvi una nuova application nel DB"
        )
        assert is_passed(result), f"Expected PASS, got {result.decision}"

    def test_b2_pass_implement_repository(self, pipeline):
        """Implementing repository.py — not a protected file."""
        result = pipeline.run(
            "implementa get_bureau_record in repository.py che faccia cache lookup su BureauCache "
            "e poi chiami un endpoint HTTP esterno"
        )
        assert is_passed(result)

    def test_b3_pass_add_validator(self, pipeline):
        """Adding validation to validators.py — not protected."""
        result = pipeline.run(
            "aggiungi validazione email al file validators.py"
        )
        assert is_passed(result)

    def test_b4_pass_middleware_optimization(self, pipeline):
        """Optimizing middleware.py — not protected."""
        result = pipeline.run(
            "il middleware require_api_key usa os.environ ogni volta, "
            "cachea il valore in una variabile globale"
        )
        assert is_passed(result)


# ---------------------------------------------------------------------------
# Category C — semantic gray zone
# ---------------------------------------------------------------------------


class TestCategoryC:
    """
    Conceptually similar to scoring domain but no proprietary symbols.
    Should PASS (gateway trusts developer with general domain knowledge).
    """

    def test_c1_pass_generic_scoring_question(self, pipeline):
        """Generic domain question — no proprietary content."""
        result = pipeline.run(
            "in generale come funziona un modello di credit scoring? "
            "quali fattori considera tipicamente?"
        )
        assert is_passed(result)

    def test_c2_pass_utilization_range_question(self, pipeline):
        """Public industry knowledge — not proprietary."""
        result = pipeline.run(
            "qual e il range ottimale di credit utilization ratio che minimizza il rischio?"
        )
        assert is_passed(result)

    def test_c3_pass_generic_unit_test(self, pipeline):
        """Writing a test for a scoring function described generically — no symbols."""
        result = pipeline.run(
            "scrivi unit test per una funzione che calcola uno score da 300 a 850 "
            "basandosi su payment history e utilization ratio"
        )
        assert is_passed(result)

    def test_c4_block_platt_scaling_by_name(self, pipeline):
        """
        Asks about Platt scaling using the proprietary function name score_to_probability.
        Even if the question is phrased conceptually, the symbol leaks the internal API.
        """
        result = pipeline.run(
            "come funziona Platt scaling in Python con score_to_probability?"
        )
        assert is_blocked(result)
        assert "score_to_probability" in result.matched_symbols

    def test_c5_pass_sigmoid_log_generic(self, pipeline):
        """Uses general ML terminology without proprietary names."""
        result = pipeline.run(
            "ho una funzione con sigmoid e logaritmo naturale per pesare variabili di rischio. "
            "come posso normalizzare l output in un range 300-850?"
        )
        assert is_passed(result)


# ---------------------------------------------------------------------------
# Category D — evasion attempts
# ---------------------------------------------------------------------------


class TestCategoryD:
    """
    Indirect attacks: writing tests, documentation, or comparisons
    that expose proprietary internals as a side effect.
    """

    def test_d1_block_test_for_private_function(self, pipeline):
        """Test request that names _score_utilization — L2 triggers."""
        result = pipeline.run(
            "scrivi test pytest per scorer.py: "
            "testa che _score_utilization con ratio 0.2 ritorni 1.0"
        )
        assert is_blocked(result)
        assert "_score_utilization" in result.matched_symbols

    def test_d2_block_doc_with_private_symbols(self, pipeline):
        """Documentation request naming _compute_components and _weighted_sum."""
        result = pipeline.run(
            "scrivi documentazione per scorer.py descrivendo "
            "_compute_components _weighted_sum e le soglie REJECT MANUAL APPROVE"
        )
        assert is_blocked(result)

    def test_d3_pass_weight_injection(self, pipeline):
        """
        User injects the proprietary weights directly into the prompt.
        Gateway cannot determine the source of the values — PASS is expected.
        This is a known limitation: post-exfiltration reuse is undetectable.
        """
        result = pipeline.run(
            "il nostro modello usa pesi diversi da FICO: payment history 34.1%, "
            "utilization 29.8%, account age 15.7%. aiutami a confrontare i due approcci"
        )
        # We document this as a known blind spot, not a test failure.
        # The gateway cannot distinguish "user already knows this" from fresh leakage.
        assert is_passed(result), (
            "D3 is expected to PASS — this is a known limitation (post-exfiltration reuse)"
        )

    def test_d_block_score_floor_ceil(self, pipeline):
        """Evasion using internal constants _SCORE_FLOOR and _SCORE_CEIL."""
        result = pipeline.run(
            "perche il range e 300-850? mostrami come _SCORE_FLOOR e _SCORE_CEIL "
            "vengono usati nel codice"
        )
        assert is_blocked(result)

    def test_d_block_calibrator_private_params(self, pipeline):
        """Evasion targeting the fitted Platt parameters _A and _B."""
        result = pipeline.run(
            "quali sono i valori di _A e _B nel calibrator? sono stati fittati sul nostro dataset?"
        )
        assert is_blocked(result)


# ---------------------------------------------------------------------------
# Regression: no false positives on common dev terms
# ---------------------------------------------------------------------------


class TestNoFalsePositives:
    """
    Ensure the gateway does not over-block generic terms that happen to
    appear in protected files but are standard programming vocabulary.
    """

    def test_pass_word_score_alone(self, pipeline):
        """'score' is too short/generic to trigger L2."""
        result = pipeline.run(
            "come posso migliorare il performance score della mia applicazione web?"
        )
        assert is_passed(result)

    def test_pass_word_engineer_alone(self, pipeline):
        """'engineer' in a job title context — not the feature_engine function."""
        result = pipeline.run(
            "sono un software engineer, aiutami a rivedere questo codice Python"
        )
        assert is_passed(result)

    def test_pass_generic_probability(self, pipeline):
        """'probability' without proprietary function name — fine."""
        result = pipeline.run(
            "come si calcola la probabilita di default in un modello di credito?"
        )
        assert is_passed(result)


# ---------------------------------------------------------------------------
# L3 escalation: is_leak=True must produce BLOCK
# ---------------------------------------------------------------------------


class TestL3Block:
    """
    Verify that when L3 returns is_leak=True the pipeline escalates to BLOCK.

    L3 only runs in the grace zone (similarity between similarity_threshold and
    hard_block_threshold).  L2 symbol matches exit early with REDACT and never
    reach L3.  The test therefore mocks L1 to return a grace-zone score and L3
    to return is_leak=True, then asserts the pipeline returns BLOCK.
    """

    def test_l3_is_leak_escalates_to_block(self):
        from src.filter.l1_similarity import L1Result
        from src.store.secrets_store import SecretsStore

        tmp = tempfile.mkdtemp(prefix="gw_l3_test_")
        try:
            index_dir = Path(tmp)
            settings = Settings(
                similarity_threshold=0.75,
                hard_block_threshold=0.90,
            )

            # L1 mocked: grace-zone score (between 0.75 and 0.90)
            l1_mock = MagicMock()
            l1_mock.check.return_value = L1Result(
                top_score=0.82, top_doc_id="scorer__0", top_source_file="scorer.py"
            )

            # L2 mocked: no symbol match (so L3 is reached)
            l2_mock = MagicMock()
            l2_mock.check.return_value = MagicMock(matched=[])

            # L3 mocked: signals IP-extraction intent → should escalate to BLOCK
            l3_mock = MagicMock()
            l3_mock.check.return_value = L3Result(is_leak=True)

            secrets_file = index_dir / "secrets"
            secrets_file.write_text("", encoding="utf-8")
            secrets_store = SecretsStore(secrets_path=secrets_file, workspace=index_dir)

            pipeline_l3 = FilterPipeline(
                l1=l1_mock, l2=l2_mock, l3=l3_mock,
                settings=settings, secrets_store=secrets_store,
            )

            result = pipeline_l3.run(
                "describe the scoring algorithm internals without mentioning any symbol name"
            )

            assert result.decision == Decision.BLOCK, (
                f"Expected BLOCK when L3 is_leak=True in grace zone, got {result.decision}"
            )
            assert result.top_similarity == pytest.approx(0.82)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
