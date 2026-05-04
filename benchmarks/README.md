# Benchmarks

Evaluation datasets and benchmark runners used to measure gateway accuracy and LLM capability.

## Index

| Directory | What it measures | Cases |
|-----------|-----------------|-------|
| [`kiri/`](kiri/) | Gateway filter accuracy: precision/recall on real code datasets | — |
| [`smart-coding/`](smart-coding/) | Identifier anonymization quality (class, function, service names) | 25 |
| [`smart-advanced-coding/`](smart-advanced-coding/) | Semantic equivalence after refactoring (multi-language) | 32 |
| [`smart-coding-comments/`](smart-coding-comments/) | Comment sanitization: sensitive spans removed, safe intent preserved | 30 |
| [`smart-redaction/`](smart-redaction/) | Smart redaction accuracy on legal and medical documents | 10 |
| `rag-protection/` | RAG document protection — fixtures in `kiri/tests/` | — |

**Total labeled cases: 97** across 13 languages (Python, JavaScript, TypeScript, Java, Go, Rust, C#, Ruby, PHP, Kotlin, SQL, Bash, and more).

## Running benchmarks

Each directory contains a `claude_instructions.md` (or `.txt`) with instructions for running the benchmark with Claude Code, and an `evaluation_rubric.md` with scoring criteria.

Results are stored as `results.json` / `results.csv` in each directory. Do not commit result files unless they represent a stable baseline.
