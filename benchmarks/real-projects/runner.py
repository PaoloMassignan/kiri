#!/usr/bin/env python3
"""
Kiri — Real-Projects Benchmark Runner

Tests the full FilterPipeline against realistic developer prompts drawn from
10 well-known open-source projects.  For each project a fixture.yaml defines
the protected symbols and the expected decision (REDACT / PASS) for each case.

Three attack scenarios per project:
  explain  — developer asks Claude Code to explain a protected class
  use      — developer asks how to use a protected class in new code
  refactor — developer asks to refactor existing code that calls a protected class

Plus one baseline:
  pass     — realistic prompt with no protected symbols present

Usage
-----
  # from repo root (requires kiri venv or kiri deps installed):
  python benchmarks/real-projects/runner.py
  python benchmarks/real-projects/runner.py --project flask
  python benchmarks/real-projects/runner.py --verbose

  # or from this directory:
  python runner.py --project gin

How to reproduce manually (requires a running Kiri workspace):
  kiri add @Flask @Scaffold
  kiri inspect --file fixtures/flask/prompts/flask-001.txt

Pipeline mode
-------------
L2 : real SymbolStore populated from fixture protected_symbols
L1 : NullVectorStore + NullEmbedder — always scores 0.0 (no indexed files)
L3 : real L3Filter, fails open if Ollama unavailable

This mirrors the production scenario where a developer has registered
explicit @symbols but has not yet indexed any source files.
"""

import sys
import tempfile
from collections import defaultdict
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed.  Run: pip install pyyaml")
    sys.exit(1)

BASE = Path(__file__).parent
KIRI_ROOT = BASE.parent.parent / "kiri"
VERBOSE = "--verbose" in sys.argv
PROJECT_FILTER = next(
    (sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--project"), None
)

# ── Kiri imports ──────────────────────────────────────────────────────────────

if not KIRI_ROOT.exists():
    print(f"ERROR: kiri/ not found at {KIRI_ROOT}")
    sys.exit(1)

sys.path.insert(0, str(KIRI_ROOT))
try:
    from src.filter.pipeline import FilterPipeline   # type: ignore
    from src.filter.l1_similarity import L1Filter    # type: ignore
    from src.filter.l2_symbols import L2Filter       # type: ignore
    from src.filter.l3_classifier import L3Filter    # type: ignore
    from src.store.symbol_store import SymbolStore   # type: ignore
    from src.config.settings import Settings         # type: ignore
except ImportError as exc:
    print(f"ERROR: cannot import from kiri/src: {exc}")
    print("Make sure you are running inside the kiri virtual environment.")
    sys.exit(1)


class _NullEmbedder:
    _DIM = 384

    def embed_one(self, text: str) -> list[float]:  # noqa: ARG002
        return [0.0] * self._DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * self._DIM for _ in texts]


class _NullVectorStore:
    """In-memory stub — always empty, no ChromaDB files on disk."""

    def query(self, vector: list[float], top_k: int) -> list:  # noqa: ARG002
        return []


# ── Pipeline ──────────────────────────────────────────────────────────────────

def classify(symbols: list[str], prompt: str) -> str:
    """Run prompt through FilterPipeline. Returns 'REDACT', 'PASS', or 'BLOCK'."""
    with tempfile.TemporaryDirectory() as tmp:
        index_dir = Path(tmp) / "index"
        index_dir.mkdir()

        store = SymbolStore(index_dir)
        if symbols:
            store.add_explicit(symbols)

        settings = Settings(workspace=Path(tmp))
        l1 = L1Filter(vector_store=_NullVectorStore(), embedder=_NullEmbedder())
        l2 = L2Filter(store)
        l3 = L3Filter(settings)

        pipeline = FilterPipeline(settings=settings, l1=l1, l2=l2, l3=l3, secrets_store=None)
        result = pipeline.run(prompt)
        return result.decision.value.upper(), result.matched_symbols


# ── Metrics ───────────────────────────────────────────────────────────────────

SEP = "-" * 62


def fmt(v: float) -> str:
    return f"{v:.3f}"


def metrics(tp: int, fp: int, fn: int, tn: int) -> dict:
    total = tp + fp + fn + tn
    p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
    acc = (tp + tn) / total if total > 0 else 0.0
    return dict(precision=p, recall=r, f1=f1, accuracy=acc,
                tp=tp, fp=fp, fn=fn, tn=tn, total=total)


# ── Project runner ────────────────────────────────────────────────────────────

def run_project(fixture_dir: Path) -> dict:
    fixture = yaml.safe_load((fixture_dir / "fixture.yaml").read_text(encoding="utf-8"))
    project  = fixture["project"]
    symbols  = [s["text"] for s in fixture.get("protected_symbols", [])]
    cases    = fixture.get("cases", [])

    print(f"\n{'=' * 62}")
    print(f"  PROJECT : {project}  ({fixture.get('language', '?')})")
    print(f"  Repo    : {fixture.get('repo', '-')}")
    print(f"  Symbols : {symbols}")
    print(f"{'=' * 62}")

    tp = fp = fn = tn = 0
    by_scenario: dict[str, dict] = defaultdict(lambda: {"ok": 0, "total": 0})

    for c in cases:
        prompt   = c["prompt"]
        expected = c["expected_action"].upper()
        decision, matched = classify(symbols, prompt)

        scored  = "REDACT" if decision in ("REDACT", "BLOCK") else "PASS"
        correct = scored == expected

        by_scenario[c["scenario"]]["total"] += 1
        if correct:
            by_scenario[c["scenario"]]["ok"] += 1

        if expected == "REDACT" and scored == "REDACT":
            tp += 1
        elif expected == "PASS" and scored == "REDACT":
            fp += 1
        elif expected == "REDACT" and scored == "PASS":
            fn += 1
        else:
            tn += 1

        if VERBOSE or not correct:
            mark = "OK" if correct else "XX"
            sym_info = f"  matched={matched}" if matched else ""
            print(f"  {mark} {c['id']:18s} [{c['scenario']:8s}]  "
                  f"expected={expected:6s}  got={scored:6s}{sym_info}")

    m = metrics(tp, fp, fn, tn)
    print(f"\n  {SEP}")
    print(f"  Cases: {m['total']}   TP={tp}  FP={fp}  FN={fn}  TN={tn}")
    print(f"  Precision={fmt(m['precision'])}  Recall={fmt(m['recall'])}  "
          f"F1={fmt(m['f1'])}  Accuracy={fmt(m['accuracy'])}")
    if not VERBOSE:
        print(f"  Scenarios:")
        for sc, v in sorted(by_scenario.items()):
            pct = v["ok"] / v["total"] if v["total"] else 0
            print(f"    {sc:10s}  {v['ok']}/{v['total']}  ({pct:.0%})")
    return {**m, "project": project}


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    fixtures_root = BASE / "fixtures"
    all_dirs = sorted(
        d for d in fixtures_root.iterdir()
        if d.is_dir() and (d / "fixture.yaml").exists()
    )

    if PROJECT_FILTER:
        all_dirs = [d for d in all_dirs if d.name == PROJECT_FILTER]
        if not all_dirs:
            available = [d.name for d in sorted(fixtures_root.iterdir()) if d.is_dir()]
            print(f"ERROR: project {PROJECT_FILTER!r} not found.  Available: {available}")
            sys.exit(1)

    print(f"\n{'=' * 62}")
    print(f"  Kiri -- Real-Projects Benchmark")
    print(f"  {len(all_dirs)} project(s)   pipeline: L2->L1->L3 (null embedder)")
    print(f"{'=' * 62}")

    results = [run_project(d) for d in all_dirs]

    if len(results) < 2:
        print()
        return

    agg = {k: sum(r[k] for r in results) for k in ("tp", "fp", "fn", "tn")}
    m = metrics(**agg)
    total_cases = sum(r["total"] for r in results)

    print(f"\n{'=' * 62}")
    print(f"  OVERALL  ({len(results)} projects, {total_cases} cases)")
    print(f"{'=' * 62}")
    print(f"  Precision : {fmt(m['precision'])}")
    print(f"  Recall    : {fmt(m['recall'])}")
    print(f"  F1        : {fmt(m['f1'])}")
    print(f"  Accuracy  : {fmt(m['accuracy'])}")
    print(f"\n  Confusion matrix:")
    print(f"                Predicted REDACT   Predicted PASS")
    print(f"  Actual REDACT    {agg['tp']:5d} (TP)        {agg['fn']:5d} (FN)")
    print(f"  Actual PASS      {agg['fp']:5d} (FP)        {agg['tn']:5d} (TN)")
    print(f"\n  Per project:")
    for r in results:
        bar = "#" * int(r["accuracy"] * 20)
        print(f"    {r['project']:22s}  {r['accuracy']:.0%}  {bar}")
    print()


if __name__ == "__main__":
    main()
