# Benchmarks

Evaluation datasets and benchmark runners used to measure gateway accuracy and LLM capability.

## Schema

All datasets follow the detect+REDACT schema aligned with Kiri's actual filter behavior:

| Field | Description |
|-------|-------------|
| `id` | Unique case identifier |
| `language` | Source language |
| `scenario` | Task verb: `refactor`, `debug`, `optimize`, `explain`, `summarize` |
| `developer_prompt` | Natural developer request with code (as sent to the proxy) |
| `registered_symbols` | Symbols registered in `.kiri/secrets` (L2 matching) |
| `expected_action` | `"REDACT"` (protected symbol detected) or `"PASS"` (no match) |
| `expected_utility` | What LLM can still do after REDACT |

`smart-coding-comments` also includes `sensitive_spans` (L1/L3 inline detection) and `detection_layer: "L1_L3"`.

`smart-advanced-coding` also includes `utility_tests` (behavioral equivalence checks).

## Index

| Directory | What it measures | Cases |
|-----------|-----------------|-------|
| [`kiri/`](kiri/) | Gateway filter accuracy: precision/recall on real code datasets | — |
| [`smart-coding/`](smart-coding/) | L2 symbol detection: REDACT vs PASS on proprietary identifiers | 82 (58 REDACT + 24 PASS) |
| [`smart-advanced-coding/`](smart-advanced-coding/) | LLM utility preserved after REDACT (multi-language) | 64 |
| [`smart-coding-comments/`](smart-coding-comments/) | L1/L3 inline sensitivity: sensitive comment spans detected | 60 |
| [`smart-redaction/`](smart-redaction/) | Smart redaction accuracy on legal and medical documents | 10 |
| `rag-protection/` | RAG document protection — fixtures in `kiri/tests/` | — |

**Total labeled cases: 216** across 15 languages (Python, JavaScript, TypeScript, Java, Go, Rust, C#, Ruby, PHP, Kotlin, SQL, Bash, Swift, Scala, and more).

`smart-coding` includes 17 near-miss cases (NM001–NM017) that stress-test word-boundary precision:
version suffixes (`RiskScorerV2`), underscore extensions (`calculate_fee_async`), case mismatches
(`InvoiceService` vs `invoice_service`), design-pattern suffixes (`FeatureStoreClient`), and
symbol detection in non-obvious positions (string literals, type annotations, imports, doc comments).

## Running benchmarks

Each directory contains a `claude_instructions.md` (or `.txt`) with instructions for running the benchmark with Claude Code, and an `evaluation_rubric.md` with scoring criteria.

Results are stored as `results.json` / `results.csv` in each directory. Do not commit result files unless they represent a stable baseline.
