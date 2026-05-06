# Benchmarks

Evaluation datasets and runners used to measure Kiri's filter accuracy.

## Index

| Directory | Role | Cases |
|-----------|------|-------|
| [`real-projects/`](real-projects/) | **Benchmark** — full FilterPipeline on 10 real open-source projects, 8 languages | 40 |
| [`smart-coding/`](smart-coding/) | **Benchmark** — L2 precision/recall/F1 on symbol detection | 105 (94 scored + 11 known failures) |
| [`smart-advanced-coding/`](smart-advanced-coding/) | **Corpus fixture** — labeled utility-after-REDACT examples | 64 |
| [`smart-coding-comments/`](smart-coding-comments/) | **Corpus fixture** — labeled L1/L3 inline sensitivity spans | 60 |

**Total: 269 cases** across 15+ languages.

`_archived/` contains the smart-redaction dataset (legal/medical document
redaction — not Kiri's core use case).

---

## real-projects — the primary benchmark

40 cases drawn from real open-source code (Flask, Requests, FastAPI, Express,
NestJS, Spring Boot, Kafka, Gin, actix-web, ASP.NET Core).  Each project has
two protected symbols and four scenarios: `explain`, `use`, `refactor`, `pass`.

```bash
python benchmarks/real-projects/runner.py
python benchmarks/real-projects/runner.py --project flask
python benchmarks/real-projects/runner.py --verbose
```

See [`real-projects/README.md`](real-projects/README.md) for full details and
instructions on how to reproduce each case with `kiri inspect`.

---

## smart-coding — L2 unit benchmark

105 cases testing L2 symbol detection in isolation.  Includes 11 documented
known-failure cases (`detection_gap: true`) with full L1/L2/L3 architecture
analysis explaining why each case is a blind spot.

```bash
# Simulation (no kiri install required)
python run_benchmarks.py --suite smart-coding

# Full FilterPipeline (requires kiri venv)
python run_benchmarks.py --suite smart-coding --pipeline
```

### smart-coding case breakdown

- **C001–C050** (50): core REDACT — proprietary symbols in realistic prompts
- **OS001–OS012** (12): open-source framework patterns (SQLAlchemy, PyTorch, NestJS, Spring Boot, AWS Lambda, Go dispatch, MediatR, Rails, ...)
- **TN001–TN015** (15): true-negative PASS — no protected symbols
- **NM001–NM017** (17): near-miss — word-boundary stress tests (version suffixes, case mismatches, separators, string literals, type annotations)
- **KF001–KF011** (11): known failures — L2 blind spots (runtime construction, aliases, naming convention gaps, Java Impl suffix, duck typing, numeric units, IaC)

---

## Runner flags

```bash
# top-level runner (smart-coding / smart-advanced-coding / smart-coding-comments)
python run_benchmarks.py                       # simulation
python run_benchmarks.py --real                # real L2Filter only
python run_benchmarks.py --pipeline            # full L2->L1->L3 pipeline
python run_benchmarks.py --suite smart-coding  # single suite
python run_benchmarks.py --verbose             # print every case

# real-projects runner
python benchmarks/real-projects/runner.py
python benchmarks/real-projects/runner.py --project gin
python benchmarks/real-projects/runner.py --verbose
```
