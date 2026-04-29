# Benchmarks

Evaluation datasets and benchmark runners used to measure gateway accuracy and LLM capability.

## Index

| Directory | What it measures |
|-----------|-----------------|
| [`kiri/`](kiri/) | Gateway filter accuracy: precision/recall on real code datasets |
| [`smart-coding/`](smart-coding/) | LLM semantic equivalence for code generation |
| [`smart-advanced-coding/`](smart-advanced-coding/) | Advanced semantic equivalence (multi-language) |
| [`smart-coding-comments/`](smart-coding-comments/) | Comment sanitization quality |
| [`smart-redaction/`](smart-redaction/) | Smart redaction accuracy on legal and code documents |
| `rag-protection/` | RAG document protection — fixtures in `kiri/tests/` (benchmark runner in mvp/backend, fuori da questo repo) |

## Running benchmarks

Each directory contains a `claude_instructions.md` (or `.txt`) with instructions for running the benchmark with Claude Code, and an `evaluation_rubric.md` with scoring criteria.

Results are stored as `results.json` / `results.csv` in each directory. Do not commit result files unless they represent a stable baseline.
