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

| Directory | Role | Cases |
|-----------|------|-------|
| [`smart-coding/`](smart-coding/) | **Benchmark** — L2 precision/recall/F1 on symbol detection | 105 (94 scored + 11 known failures) |
| [`smart-advanced-coding/`](smart-advanced-coding/) | **Corpus fixture** — labeled utility-after-REDACT examples | 64 |
| [`smart-coding-comments/`](smart-coding-comments/) | **Corpus fixture** — labeled L1/L3 inline sensitivity spans | 60 |
| [`smart-redaction/`](smart-redaction/) | **Benchmark** — smart redaction on legal/medical documents | 10 |
| [`kiri/`](kiri/) | Gateway filter accuracy on real code datasets | — |
| `rag-protection/` | RAG document protection — fixtures in `kiri/tests/` | — |

**Total labeled cases: 239** across 15+ languages (Python, JavaScript, TypeScript, Java, Go, Rust, C#, Ruby, PHP, Kotlin, SQL, Bash, Swift, Scala, YAML, and more).

### smart-coding breakdown (105 cases)

- **C001–C050** (50): core REDACT cases — proprietary symbols in realistic developer prompts
- **OS001–OS012** (12): open-source-framework patterns — SQLAlchemy, Apache Beam, PyTorch, NestJS, Spring Boot, AWS Lambda, Go dispatch, C# MediatR, Rails ActiveJob — realistic proprietary class names
- **TN001–TN015** (15): true-negative PASS cases — no protected symbols present
- **NM001–NM017** (17): near-miss cases — stress-test word-boundary precision: version suffixes (`RiskScorerV2`), underscore extensions (`calculate_fee_async`), case mismatches (`InvoiceService` vs `invoice_service`), design-pattern suffixes (`FeatureStoreClient`), symbol in non-obvious positions (string literals, type annotations, imports, doc comments)
- **KF001–KF011** (11): known-failure cases (`detection_gap: true`) — L2 blind spots excluded from F1 scoring, documented with full L1/L2/L3 architecture analysis. Categories: runtime string construction, alias/partial context, naming convention gaps, Java Impl suffix, interface/duck typing, numeric unit mismatch, numeric sig-fig precision, Infrastructure-as-Code

## Running benchmarks

```bash
# Simulation (regex mirrors kiri/src/filter/l2_symbols.py)
python run_benchmarks.py

# Real L2Filter only — imports actual SymbolStore + L2Filter from kiri/src
python run_benchmarks.py --real

# Full FilterPipeline — real L2->L1->L3 code path, null embedder + empty
# VectorStore (no indexed files, no Ollama required). Reflects the production
# scenario where only explicit @symbols are registered.
python run_benchmarks.py --pipeline

# Single suite
python run_benchmarks.py --suite smart-coding --pipeline

# Verbose: print every case
python run_benchmarks.py --verbose
```

Results are stored as `results.json` / `results.csv` in each directory. Do not commit result files unless they represent a stable baseline.
