#!/usr/bin/env python3
"""
Kiri -- Real-Projects Benchmark Runner

Tests the full FilterPipeline against realistic developer prompts drawn from
10 well-known open-source projects.

Two tiers of cases per project
-------------------------------
easy (cases)       L2 only -- symbol appears verbatim in the prompt.
                   Uses NullEmbedder + NullVectorStore: no external calls,
                   no Ollama required.  Expected F1 ~ 1.0.

hard (hard_cases)  L1 + L2 + L3 -- symbol does NOT appear verbatim.
                   The project's source code is indexed with the real
                   sentence-transformers embedder (all-MiniLM-L6-v2).
                   L1 fires on semantic similarity; L3 (Ollama qwen2.5:3b)
                   arbitrates the grace zone 0.75-0.90.
                   Expected F1 < 1.0 -- documents genuine L1 capabilities
                   and gaps.

Usage
-----
  python benchmarks/real-projects/runner.py
  python benchmarks/real-projects/runner.py --project flask
  python benchmarks/real-projects/runner.py --verbose
  python benchmarks/real-projects/runner.py --easy-only
  python benchmarks/real-projects/runner.py --hard-only
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
EASY_ONLY = "--easy-only" in sys.argv
HARD_ONLY = "--hard-only" in sys.argv
PROJECT_FILTER = next(
    (sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--project"), None
)

# ── Kiri imports ──────────────────────────────────────────────────────────────

if not KIRI_ROOT.exists():
    print(f"ERROR: kiri/ not found at {KIRI_ROOT}")
    sys.exit(1)

sys.path.insert(0, str(KIRI_ROOT))
try:
    from src.filter.pipeline import FilterPipeline            # type: ignore
    from src.filter.l1_similarity import L1Filter             # type: ignore
    from src.filter.l2_symbols import L2Filter                # type: ignore
    from src.filter.l3_classifier import L3Filter             # type: ignore
    from src.store.symbol_store import SymbolStore            # type: ignore
    from src.store.vector_store import QueryResult            # type: ignore
    from src.config.settings import Settings                  # type: ignore
except ImportError as exc:
    print(f"ERROR: cannot import from kiri/src: {exc}")
    sys.exit(1)

# ── Null stubs (easy-case mode) ───────────────────────────────────────────────

class _NullEmbedder:
    _DIM = 384

    def embed_one(self, text: str) -> list[float]:  # noqa: ARG002
        return [0.0] * self._DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * self._DIM for _ in texts]


class _NullVectorStore:
    def query(self, vector: list[float], top_k: int) -> list:  # noqa: ARG002
        return []


# ── In-memory vector store (hard-case mode) ───────────────────────────────────

class _InMemoryVectorStore:
    """ChromaDB EphemeralClient — no files on disk, no Windows file-lock issues."""

    def __init__(self) -> None:
        import chromadb
        self._col = chromadb.EphemeralClient().get_or_create_collection(
            "kiri_bench", metadata={"hnsw:space": "cosine"}
        )

    def add(self, doc_id: str, vector: list[float], metadata: dict) -> None:
        self._col.upsert(ids=[doc_id], embeddings=[vector], metadatas=[metadata])

    def query(self, vector: list[float], top_k: int) -> list[QueryResult]:
        n = min(top_k, self._col.count())
        if n == 0:
            return []
        raw = self._col.query(
            query_embeddings=[vector],
            n_results=n,
            include=["distances", "metadatas"],
        )
        return [
            QueryResult(
                doc_id=did,
                similarity=round(1.0 - dist / 2.0, 6),
                source_file=meta["source_file"],
                chunk_index=int(meta["chunk_index"]),
            )
            for did, dist, meta in zip(
                raw["ids"][0], raw["distances"][0], raw["metadatas"][0]
            )
        ]


# ── Classify helpers ──────────────────────────────────────────────────────────

def _make_pipeline(symbols, l1, settings, tmp_path):
    index_dir = tmp_path / "index"
    index_dir.mkdir(exist_ok=True)
    store = SymbolStore(index_dir)
    if symbols:
        store.add_explicit(symbols)
    return FilterPipeline(
        settings=settings,
        l1=l1,
        l2=L2Filter(store),
        l3=L3Filter(settings),
        secrets_store=None,
    )


def classify_easy(symbols: list[str], prompt: str) -> tuple[str, list[str], float, str]:
    """L2-only: NullEmbedder + NullVectorStore."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        settings = Settings(workspace=tmp_path)
        l1 = L1Filter(vector_store=_NullVectorStore(), embedder=_NullEmbedder())
        pipeline = _make_pipeline(symbols, l1, settings, tmp_path)
        r = pipeline.run(prompt)
        return r.decision.value.upper(), r.matched_symbols, r.top_similarity, r.reason


def classify_full(
    symbols: list[str],
    prompt: str,
    source_files: list[dict],
) -> tuple[str, list[str], float, str]:
    """Full pipeline: real Embedder (L1), SymbolStore (L2), Ollama L3."""
    from src.indexer.chunker import chunk as do_chunk  # type: ignore
    from src.indexer.embedder import Embedder           # type: ignore

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        settings = Settings(workspace=tmp_path)
        embedder = Embedder(settings=settings)
        vs = _InMemoryVectorStore()

        for sf in source_files:
            src_path = tmp_path / sf["filename"]
            src_path.write_text(sf["content"], encoding="utf-8")
            chunks = do_chunk(src_path)
            if not chunks:
                continue
            vectors = embedder.embed([c.text for c in chunks])
            for i, (ch, vec) in enumerate(zip(chunks, vectors)):
                vs.add(
                    f"{sf['filename']}__{i}",
                    vec,
                    {"source_file": sf["filename"], "chunk_index": str(i)},
                )

        l1 = L1Filter(vector_store=vs, embedder=embedder)
        pipeline = _make_pipeline(symbols, l1, settings, tmp_path)
        r = pipeline.run(prompt)
        return r.decision.value.upper(), r.matched_symbols, r.top_similarity, r.reason


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


def _run_cases(
    cases: list[dict],
    symbols: list[str],
    classify_fn,
    label: str,
) -> dict:
    if not cases:
        return {}

    tp = fp = fn = tn = 0
    by_scenario: dict[str, dict] = defaultdict(lambda: {"ok": 0, "total": 0})

    for c in cases:
        prompt = c["prompt"]
        expected = c["expected_action"].upper()
        decision, matched, score, reason = classify_fn(symbols, prompt)

        scored = "REDACT" if decision in ("REDACT", "BLOCK") else "PASS"
        correct = scored == expected

        scenario = c.get("scenario", "?")
        by_scenario[scenario]["total"] += 1
        if correct:
            by_scenario[scenario]["ok"] += 1

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
            score_str = f"  sim={score:.3f}" if score > 0 else ""
            sym_str = f"  matched={matched}" if matched else ""
            print(f"  {mark} {c['id']:20s} [{scenario:16s}]  "
                  f"expected={expected:6s}  got={scored:6s}{score_str}{sym_str}")
            if not correct and not VERBOSE:
                print(f"       reason: {reason}")

    m = metrics(tp, fp, fn, tn)
    print(f"\n  {SEP}")
    print(f"  {label}: {m['total']} cases   "
          f"TP={tp}  FP={fp}  FN={fn}  TN={tn}")
    print(f"  Precision={fmt(m['precision'])}  Recall={fmt(m['recall'])}  "
          f"F1={fmt(m['f1'])}  Accuracy={fmt(m['accuracy'])}")

    if not VERBOSE:
        print(f"  Scenarios:")
        for sc, v in sorted(by_scenario.items()):
            pct = v["ok"] / v["total"] if v["total"] else 0.0
            print(f"    {sc:20s}  {v['ok']}/{v['total']}  ({pct:.0%})")

    return m


# ── Project runner ────────────────────────────────────────────────────────────

def run_project(fixture_dir: Path) -> dict:
    fixture = yaml.safe_load((fixture_dir / "fixture.yaml").read_text(encoding="utf-8"))
    project      = fixture["project"]
    symbols      = [s["text"] for s in fixture.get("protected_symbols", [])]
    easy_cases   = fixture.get("cases", [])
    hard_cases   = fixture.get("hard_cases", [])
    source_files = fixture.get("source_files", [])

    print(f"\n{'=' * 62}")
    print(f"  PROJECT : {project}  ({fixture.get('language', '?')})")
    print(f"  Repo    : {fixture.get('repo', '-')}")
    print(f"  Symbols : {symbols}")
    print(f"{'=' * 62}")

    easy_m = hard_m = {}

    if not HARD_ONLY and easy_cases:
        print(f"\n  -- EASY (L2 only) --")
        easy_m = _run_cases(easy_cases, symbols, classify_easy, "Easy cases")

    if not EASY_ONLY and hard_cases and source_files:
        print(f"\n  -- HARD (L1 + L2 + L3, Ollama active) --")
        classify_hard = lambda sym, prompt: classify_full(sym, prompt, source_files)  # noqa: E731
        hard_m = _run_cases(hard_cases, symbols, classify_hard, "Hard cases")
    elif not EASY_ONLY and hard_cases and not source_files:
        print("  [WARN] hard_cases defined but no source_files — skipping hard tier")

    return {"project": project, "easy": easy_m, "hard": hard_m}


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

    tier = "hard only" if HARD_ONLY else ("easy only" if EASY_ONLY else "easy + hard")
    print(f"\n{'=' * 62}")
    print(f"  Kiri -- Real-Projects Benchmark  [{tier}]")
    print(f"  {len(all_dirs)} project(s)")
    print(f"{'=' * 62}")

    results = [run_project(d) for d in all_dirs]

    if len(results) < 2:
        print()
        return

    def _agg(tier_key: str) -> dict | None:
        tier_results = [r[tier_key] for r in results if r[tier_key]]
        if not tier_results:
            return None
        agg = {k: sum(r[k] for r in tier_results) for k in ("tp", "fp", "fn", "tn")}
        return metrics(**agg)

    print(f"\n{'=' * 62}")
    print(f"  OVERALL  ({len(results)} projects)")
    print(f"{'=' * 62}")

    for label, key in [("Easy (L2)", "easy"), ("Hard (L1+L2+L3)", "hard")]:
        m = _agg(key)
        if m:
            print(f"\n  {label}:")
            print(f"    Precision={fmt(m['precision'])}  "
                  f"Recall={fmt(m['recall'])}  "
                  f"F1={fmt(m['f1'])}  "
                  f"Accuracy={fmt(m['accuracy'])}")
            print(f"    TP={m['tp']}  FP={m['fp']}  FN={m['fn']}  TN={m['tn']}  "
                  f"total={m['total']}")

    print(f"\n  Per-project:")
    for r in results:
        parts = []
        if r["easy"]:
            parts.append(f"easy={r['easy']['accuracy']:.0%}")
        if r["hard"]:
            parts.append(f"hard={r['hard']['accuracy']:.0%}")
        print(f"    {r['project']:22s}  {', '.join(parts)}")
    print()


if __name__ == "__main__":
    main()
