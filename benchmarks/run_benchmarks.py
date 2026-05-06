#!/usr/bin/env python3
"""
Kiri benchmark runner — detect+REDACT schema.

Suites:
  smart-coding          -> L2 classification (REDACT/PASS)  -- precision/recall/F1
  smart-advanced-coding -> utility-after-REDACT             -- symbol presence check
  smart-coding-comments -> L1/L3 inline detection           -- span coverage stats

Usage:
  python run_benchmarks.py
  python run_benchmarks.py --suite smart-coding
  python run_benchmarks.py --verbose
  python run_benchmarks.py --real        # real L2Filter from kiri/src (L2 only)
  python run_benchmarks.py --pipeline    # full FilterPipeline: L2->L1->L3
"""
import json
import re
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).parent
VERBOSE = "--verbose" in sys.argv
SUITE_FILTER = next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--suite"), None)
USE_REAL = "--real" in sys.argv
USE_PIPELINE = "--pipeline" in sys.argv

SEP = "-" * 62

# ── Real L2Filter setup (only when --real) ───────────────────────────────────

_real_l2_available = False
_L2Filter = None
_SymbolStore = None

if USE_REAL:
    kiri_root = BASE.parent / "kiri"
    if kiri_root.exists():
        sys.path.insert(0, str(kiri_root))
        try:
            from src.filter.l2_symbols import L2Filter as _L2Filter      # type: ignore
            from src.store.symbol_store import SymbolStore as _SymbolStore  # type: ignore
            _real_l2_available = True
        except ImportError as e:
            print(f"  [WARN] --real requested but import failed: {e}")
            print("  [WARN] Falling back to simulation.")
    else:
        print(f"  [WARN] --real requested but kiri/ not found at {kiri_root}")

# ── Full FilterPipeline setup (only when --pipeline) ─────────────────────────

_pipeline_available = False
_FilterPipeline = None
_FilterDecision = None
_L1Filter = None
_L2Filter_p = None
_L3Filter = None
_SymbolStore_p = None
_VectorStore = None
_PipelineSettings = None


class _NullEmbedder:
    """Zero-vector stub — no external calls, no model loading."""

    _DIM = 384  # all-MiniLM-L6-v2 output dimension

    def embed_one(self, text: str) -> list[float]:  # noqa: ARG002
        return [0.0] * self._DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * self._DIM for _ in texts]


class _NullVectorStore:
    """In-memory stub that always returns no results.

    Replaces ChromaDB's PersistentClient so there are no files to lock or clean
    up on Windows.  Behaviour is identical to an empty persistent store: L1 always
    scores 0.0 -> PASS, which matches production when no files have been indexed.
    """

    def query(self, vector: list[float], top_k: int) -> list:  # noqa: ARG002
        return []


if USE_PIPELINE:
    kiri_root = BASE.parent / "kiri"
    if kiri_root.exists():
        if str(kiri_root) not in sys.path:
            sys.path.insert(0, str(kiri_root))
        try:
            from src.filter.pipeline import FilterPipeline as _FilterPipeline, Decision as _FilterDecision  # type: ignore
            from src.filter.l1_similarity import L1Filter as _L1Filter              # type: ignore
            from src.filter.l2_symbols import L2Filter as _L2Filter_p               # type: ignore
            from src.filter.l3_classifier import L3Filter as _L3Filter              # type: ignore
            from src.store.symbol_store import SymbolStore as _SymbolStore_p        # type: ignore
            from src.config.settings import Settings as _PipelineSettings           # type: ignore
            _pipeline_available = True
        except ImportError as e:
            print(f"  [WARN] --pipeline requested but import failed: {e}")
            print("  [WARN] Falling back to simulation.")
    else:
        print(f"  [WARN] --pipeline requested but kiri/ not found at {kiri_root}")


def load(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


# ── L2 helpers ───────────────────────────────────────────────────────────────

def _sim_l2_matches(registered_symbols: list[dict], prompt: str) -> list[str]:
    """Simulation: word-boundary regex (mirrors kiri/src/filter/l2_symbols.py)."""
    matched = []
    for sym in registered_symbols:
        text = sym.get("text", "")
        if text and re.search(rf"\b{re.escape(text)}\b", prompt):
            matched.append(text)
    return matched


def _real_l2_matches(registered_symbols: list[dict], prompt: str) -> list[str]:
    """Use actual SymbolStore + L2Filter from kiri/src via a temp index dir."""
    texts = [s["text"] for s in registered_symbols if s.get("text")]
    if not texts:
        return []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        symbols_json = {"@explicit": texts}
        (tmp_path / "symbols.json").write_text(
            json.dumps(symbols_json), encoding="utf-8"
        )
        store = _SymbolStore(tmp_path)
        result = _L2Filter(store).check(prompt)
        return result.matched


def l2_matches(registered_symbols: list[dict], prompt: str) -> list[str]:
    if USE_REAL and _real_l2_available:
        return _real_l2_matches(registered_symbols, prompt)
    return _sim_l2_matches(registered_symbols, prompt)


def _pipeline_classify(registered_symbols: list[dict], prompt: str) -> str:
    """Run prompt through the full FilterPipeline (L2->L1->L3).

    L1 uses an empty VectorStore + _NullEmbedder so it always scores 0.0 —
    identical to production behaviour when only explicit @symbols are registered
    and no files have been indexed yet.  L3 fails open if Ollama is unavailable.
    """
    texts = [s["text"] for s in registered_symbols if s.get("text")]
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        index_dir = tmp_path / "index"
        index_dir.mkdir()

        store = _SymbolStore_p(index_dir)
        if texts:
            store.add_explicit(texts)

        settings = _PipelineSettings(workspace=tmp_path)
        l1   = _L1Filter(vector_store=_NullVectorStore(), embedder=_NullEmbedder())
        l2   = _L2Filter_p(store)
        l3   = _L3Filter(settings)

        pipeline = _FilterPipeline(settings=settings, l1=l1, l2=l2, l3=l3, secrets_store=None)
        result = pipeline.run(prompt)
        return result.decision.value.upper()


def predict_action(registered_symbols: list[dict], prompt: str) -> str:
    if USE_PIPELINE and _pipeline_available:
        decision = _pipeline_classify(registered_symbols, prompt)
        # BLOCK is not expected in any scored case; treat as REDACT for scoring
        return "REDACT" if decision in ("REDACT", "BLOCK") else "PASS"
    return "REDACT" if l2_matches(registered_symbols, prompt) else "PASS"


# ── Metrics helpers ──────────────────────────────────────────────────────────

def classification_metrics(tp: int, fp: int, fn: int, tn: int) -> dict:
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy  = (tp + tn) / (tp + fp + fn + tn) if (tp + fp + fn + tn) > 0 else 0.0
    return dict(precision=precision, recall=recall, f1=f1, accuracy=accuracy,
                tp=tp, fp=fp, fn=fn, tn=tn)


def fmt(v: float) -> str:
    return f"{v:.3f}"


# ── Suite 1: smart-coding ────────────────────────────────────────────────────

def run_smart_coding():
    print(f"\n{'=' * 62}")
    if USE_PIPELINE and _pipeline_available:
        mode = "full pipeline (L2->L1->L3, null embedder)"
    elif USE_REAL and _real_l2_available:
        mode = "real L2Filter"
    else:
        mode = "simulation"
    print(f"  SUITE: smart-coding  (L2 symbol detection)  [{mode}]")
    print(f"{'=' * 62}")

    all_cases = load(BASE / "smart-coding" / "coding_dataset.json")

    gap_cases   = [c for c in all_cases if c.get("detection_gap")]
    scorable    = [c for c in all_cases if not c.get("detection_gap")]

    tp = fp = fn = tn = 0
    errors = []
    by_language: dict[str, list] = defaultdict(list)

    for c in scorable:
        predicted = predict_action(c["registered_symbols"], c["developer_prompt"])
        expected  = c["expected_action"]
        correct   = predicted == expected

        by_language[c["language"]].append(correct)

        if expected == "REDACT" and predicted == "REDACT":
            tp += 1
        elif expected == "PASS" and predicted == "REDACT":
            fp += 1
            errors.append(c)
        elif expected == "REDACT" and predicted == "PASS":
            fn += 1
            errors.append(c)
        elif expected == "PASS" and predicted == "PASS":
            tn += 1

        if VERBOSE:
            mark = "OK" if correct else "XX"
            syms = [s["text"] for s in c["registered_symbols"]]
            matched = l2_matches(c["registered_symbols"], c["developer_prompt"])
            print(f"  {mark} {c['id']:8s} [{c['language']:12s}] "
                  f"expected={expected:6s} got={predicted:6s} "
                  f"registered={syms} matched={matched}")

    m = classification_metrics(tp, fp, fn, tn)

    print(f"\n  Scored cases  : {len(scorable)}  (REDACT={tp+fn}, PASS={tn+fp})")
    print(f"  Excluded (gaps): {len(gap_cases)}  known L2 blind spots — scored separately below")
    print(f"  {SEP}")
    print(f"  Precision : {fmt(m['precision'])}   (REDACT correctly predicted / all predicted REDACT)")
    print(f"  Recall    : {fmt(m['recall'])}   (REDACT correctly detected / all actual REDACT)")
    print(f"  F1        : {fmt(m['f1'])}")
    print(f"  Accuracy  : {fmt(m['accuracy'])}")
    print(f"\n  Confusion matrix (scorable cases only):")
    print(f"              Predicted REDACT  Predicted PASS")
    print(f"  Actual REDACT    {tp:3d} (TP)         {fn:3d} (FN)")
    print(f"  Actual PASS      {fp:3d} (FP)         {tn:3d} (TN)")

    # Per-language accuracy (scorable only)
    print(f"\n  Per-language accuracy:")
    for lang in sorted(by_language):
        results = by_language[lang]
        acc = sum(results) / len(results)
        bar = "#" * int(acc * 20)
        print(f"    {lang:15s}  {acc:.0%}  {bar}  ({sum(results)}/{len(results)})")

    if errors:
        print(f"\n  Unexpected misclassifications ({len(errors)}):")
        for c in errors:
            syms = [s["text"] for s in c["registered_symbols"]]
            matched = l2_matches(c["registered_symbols"], c["developer_prompt"])
            tag = "FP" if c["expected_action"] == "PASS" else "FN"
            print(f"    [{tag}] {c['id']}  registered={syms}  matched={matched}")
            if VERBOSE:
                print(f"         prompt: {c['developer_prompt'][:120]!r}")

    # ── Known L2 blind spots ─────────────────────────────────────────────────
    print(f"\n  {'=' * 58}")
    print(f"  KNOWN L2 BLIND SPOTS  ({len(gap_cases)} cases — expected failures)")
    print(f"  {'=' * 58}")

    COVERAGE_LABEL = {
        "covered_by_l1": "L1 covers (if file indexed)",
        "partial":        "Partial (L1 if indexed)",
        "blind_spot":     "BLIND SPOT (all layers)",
    }

    gap_categories = {
        "Runtime construction":        ["KF001", "KF004"],
        "Alias / partial context":     ["KF002"],
        "Naming convention gap":       ["KF003", "KF008", "KF009"],
        "Suffix breaks boundary":      ["KF005"],
        "Interface / duck typing":     ["KF006"],
        "Numeric representation":      ["KF007", "KF010"],
        "Infrastructure-as-Code":      ["KF011"],
    }
    id_to_case = {c["id"]: c for c in gap_cases}

    coverage_summary: Counter = Counter()
    for c in gap_cases:
        coverage_summary[c.get("full_pipeline_coverage", "unknown")] += 1

    print(f"\n  Full-pipeline coverage summary:")
    for key, label in COVERAGE_LABEL.items():
        n = coverage_summary[key]
        print(f"    {label:35s}  {n} case(s)")

    for category, ids in gap_categories.items():
        print(f"\n  [{category}]")
        for cid in ids:
            c = id_to_case.get(cid)
            if not c:
                continue
            predicted = predict_action(c["registered_symbols"], c["developer_prompt"])
            syms = [s["text"] for s in c["registered_symbols"]]
            coverage = COVERAGE_LABEL.get(c.get("full_pipeline_coverage", ""), "?")
            print(f"    {cid:6s} [{c['language']:12s}]  L2={predicted:6s}  "
                  f"pipeline: {coverage}")
            # Print gap_reason wrapped at 70 chars, first sentence only unless verbose
            reason = c.get("gap_reason", "")
            if not VERBOSE:
                reason = reason.split(". Architecture verdict:")[0] + "."
            words = reason.split()
            line = "           "
            for word in words:
                if len(line) + len(word) + 1 > 72:
                    print(line)
                    line = "           " + word
                else:
                    line += " " + word
            if line.strip():
                print(line)

    return m


# ── Suite 2: smart-advanced-coding ──────────────────────────────────────────

def run_smart_advanced_coding():
    print(f"\n{'=' * 62}")
    print("  CORPUS FIXTURE: smart-advanced-coding  (utility after REDACT)")
    print(f"{'=' * 62}")

    cases = load(BASE / "smart-advanced-coding" / "semantic_equivalence_dataset.json")

    present     = 0
    absent      = 0
    has_tests   = 0
    by_language: Counter = Counter()

    absent_cases = []
    for c in cases:
        by_language[c["language"]] += 1
        syms    = c.get("registered_symbols", [])
        prompt  = c["developer_prompt"]
        matched = l2_matches(syms, prompt)

        if matched:
            present += 1
        else:
            absent += 1
            absent_cases.append(c)

        if c.get("utility_tests"):
            has_tests += 1

        if VERBOSE:
            mark = "OK" if matched else "!!"
            print(f"  {mark} {c['id']:8s} [{c['language']:12s}] "
                  f"symbols={[s['text'] for s in syms]} matched={matched}")

    total = len(cases)
    print(f"\n  Cases          : {total}  (all expected REDACT)")
    print(f"  Symbols present: {present}/{total}  ({present/total:.0%}) — L2 would trigger REDACT")
    print(f"  With utility_tests : {has_tests}/{total}")
    print(f"\n  Languages: {dict(by_language.most_common())}")

    if absent_cases:
        print(f"\n  Cases with no registered symbol in prompt ({len(absent_cases)}):")
        for c in absent_cases:
            syms = [s["text"] for s in c.get("registered_symbols", [])]
            print(f"    {c['id']}  registered={syms}")
            print(f"      prompt[:100]: {c['developer_prompt'][:100]!r}")


# ── Suite 3: smart-coding-comments ──────────────────────────────────────────

def run_smart_coding_comments():
    print(f"\n{'=' * 62}")
    print("  CORPUS FIXTURE: smart-coding-comments  (L1/L3 inline detection)")
    print(f"{'=' * 62}")

    cases = load(BASE / "smart-coding-comments" / "comment_sanitization_dataset.json")

    label_counts: Counter = Counter()
    spans_per_case = []
    by_language: Counter = Counter()

    for c in cases:
        spans = c.get("sensitive_spans", [])
        spans_per_case.append(len(spans))
        by_language[c["language"]] += 1
        for span in spans:
            label_counts[span.get("label", "UNKNOWN")] += 1

        if VERBOSE:
            span_labels = [f"{s['text']!r}:{s['label']}" for s in spans]
            print(f"  {c['id']:8s} [{c['language']:12s}] "
                  f"scenario={c['scenario']:10s}  spans={span_labels}")

    total       = len(cases)
    total_spans = sum(spans_per_case)
    avg_spans   = total_spans / total if total else 0

    print(f"\n  Cases        : {total}  (all expected REDACT, all detection_layer=L1_L3)")
    print(f"  Total spans  : {total_spans}  (avg {avg_spans:.1f} per case)")
    print(f"\n  Span label distribution:")
    for label, count in label_counts.most_common():
        bar = "#" * int(count / total_spans * 40)
        print(f"    {label:30s}  {count:3d}  {bar}")

    print(f"\n  Languages: {dict(by_language.most_common())}")

    # Spans-per-case distribution
    dist: Counter = Counter(spans_per_case)
    print(f"\n  Spans-per-case distribution:")
    for n in sorted(dist):
        print(f"    {n} span(s) : {dist[n]} cases")


# ── Entry point ──────────────────────────────────────────────────────────────

def main():
    print(f"\n{'=' * 62}")
    print("  Kiri — Benchmark Runner")
    print(f"{'=' * 62}")

    suites = {
        "smart-coding":          run_smart_coding,
        "smart-advanced-coding": run_smart_advanced_coding,
        "smart-coding-comments": run_smart_coding_comments,
    }

    to_run = {k: v for k, v in suites.items()
              if SUITE_FILTER is None or k == SUITE_FILTER}

    if not to_run:
        print(f"  Unknown suite: {SUITE_FILTER!r}. Available: {list(suites)}")
        sys.exit(1)

    metrics = {}
    for name, fn in to_run.items():
        metrics[name] = fn()

    # Quick summary if all suites ran
    if len(metrics) == 3 and None not in metrics.values():
        m = metrics["smart-coding"]
        print(f"\n{'=' * 62}")
        print("  SUMMARY")
        print(f"{'=' * 62}")
        if USE_PIPELINE and _pipeline_available:
            label = "Full pipeline (L2->L1->L3)"
        elif USE_REAL and _real_l2_available:
            label = "Real L2Filter"
        else:
            label = "Simulation"
        print(f"  smart-coding [{label}] :")
        print(f"    Precision {fmt(m['precision'])}  "
              f"Recall {fmt(m['recall'])}  "
              f"F1 {fmt(m['f1'])}  "
              f"Accuracy {fmt(m['accuracy'])}")

    print()


if __name__ == "__main__":
    main()
