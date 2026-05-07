# Real-Projects Benchmark

End-to-end evaluation of Kiri's FilterPipeline against realistic developer
prompts drawn from 10 well-known open-source projects across 6 languages.

**Want to run this against your own code?** See [HOW_TO_BENCHMARK.md](HOW_TO_BENCHMARK.md).

---

## What this benchmark measures

For each project, 2 symbols are registered as protected (simulating a company's
proprietary IP).  Cases are split into two tiers that test different layers of
the FilterPipeline.

### Easy tier — L2 only

The protected symbol appears **verbatim** in the prompt.  L2 catches it with
word-boundary regex.  Expected F1 = 1.000.  These cases verify the baseline:
"does symbol matching work at all?"

### Hard tier — L1 + L2 + L3

The protected symbol is **absent** from the prompt.  The developer has renamed
the class, pasted a code fragment, or described the behaviour in prose.  The
project's source code is indexed with `all-MiniLM-L6-v2` and stored in an
in-memory ChromaDB collection.  L1 runs semantic similarity; cases that score
in the 0.75–0.90 grace zone are escalated to L3 (Ollama `qwen2.5:3b`).

Three hard-case scenarios per project:

| Scenario | What it tests | Typical L1 outcome |
|----------|---------------|--------------------|
| `renamed_class` | Same code, class name swapped | Catches — internal API names provide signal |
| `partial_snippet` | Method body without class context | Catches — distinctive method calls recognised |
| `semantic_reformulation` | Pure prose, no code | Often misses — documents the L1 boundary |

---

## Projects

| Project | Language | Protected symbols | Easy | Hard |
|---------|----------|-------------------|------|------|
| [flask](fixtures/flask/fixture.yaml) | Python | `Flask`, `Scaffold` | 4 | 3 |
| [requests](fixtures/requests/fixture.yaml) | Python | `Session`, `HTTPAdapter` | 4 | 2 |
| [fastapi](fixtures/fastapi/fixture.yaml) | Python | `FastAPI`, `APIRouter` | 4 | 2 |
| [express](fixtures/express/fixture.yaml) | JavaScript | `Router`, `Application` | 4 | 2 |
| [nestjs](fixtures/nestjs/fixture.yaml) | TypeScript | `NestFactory`, `Injectable` | 4 | 3 |
| [spring-boot](fixtures/spring-boot/fixture.yaml) | Java | `SpringApplication`, `ApplicationContext` | 4 | 2 |
| [kafka](fixtures/kafka/fixture.yaml) | Java | `KafkaProducer`, `KafkaConsumer` | 4 | 3 |
| [gin](fixtures/gin/fixture.yaml) | Go | `Engine`, `RouterGroup` | 4 | 2 |
| [actix-web](fixtures/actix-web/fixture.yaml) | Rust | `HttpServer`, `App` | 4 | 2 |
| [aspnetcore](fixtures/aspnetcore/fixture.yaml) | C# | `WebApplication`, `WebApplicationBuilder` | 4 | 2 |

**40 easy cases** (30 REDACT + 10 PASS) + **23 hard cases** (all REDACT expected).

---

## Results

### Easy tier

```
F1=1.000   TP=30  FP=0  FN=0  TN=10   (40 cases)
```

L2 catches every direct symbol reference.  No false positives on the PASS cases.

### Hard tier (last run)

```
Precision=1.000  Recall=0.913  F1=0.955   (23 cases)
TP=21  FP=0  FN=2
```

| FN case | sim | Reason |
|---------|-----|--------|
| `actix-web-h001` | 0.714 | Rust generic struct + design-rationale question; embedding drifts from code structure |
| `kafka-h003` | 0.747 | Generic messaging prose; vocabulary too common to uniquely identify Kafka source |

Three cases score `sim=0.000` — they are caught by L2, not L1, because the
renamed prompt leaks a protected symbol through an internal API call:
- `fastapi-h001`: `routing.APIRouter(...)` present in code body
- `gin-h001`: `RouterGroup` present as embedded struct field
- `aspnetcore-h002`: `new WebApplication(host)` present in snippet

This is a real and valid detection pattern: a developer renames a class but
continues calling the original library's API.  L2 intercepts it regardless.

---

## Running the benchmark

```bash
# Activate the Kiri virtual environment first, then from the repo root:

# Full run (both tiers):
python benchmarks/real-projects/runner.py

# Single project:
python benchmarks/real-projects/runner.py --project flask

# Hard cases only (requires Ollama running for L3):
python benchmarks/real-projects/runner.py --hard-only

# Easy cases only (no Ollama needed):
python benchmarks/real-projects/runner.py --easy-only

# Verbose — prints similarity scores for every case:
python benchmarks/real-projects/runner.py --verbose
```

Ollama must be running (`ollama serve`) for L3 to be active.  If unavailable,
L3 fails open and the grace-zone decision depends on L1's threshold alone.
