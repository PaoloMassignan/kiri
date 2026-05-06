# Real-Projects Benchmark

End-to-end evaluation of Kiri's FilterPipeline against realistic developer
prompts drawn from 10 well-known open-source projects across 8 languages.

## What this benchmark measures

For each project, two key symbols are registered as protected (simulating a
company's proprietary IP).  Each case submits a realistic Claude Code prompt
through the full `FilterPipeline` (L2 -> L1 -> L3) and checks the decision
against the expected outcome.

**Metrics**: precision, recall, F1, accuracy per project and overall.

## Projects

| Project | Language | Protected symbols | Cases |
|---------|----------|-------------------|-------|
| [flask](fixtures/flask/fixture.yaml) | Python | `Flask`, `Scaffold` | 4 |
| [requests](fixtures/requests/fixture.yaml) | Python | `Session`, `HTTPAdapter` | 4 |
| [fastapi](fixtures/fastapi/fixture.yaml) | Python | `FastAPI`, `APIRouter` | 4 |
| [express](fixtures/express/fixture.yaml) | JavaScript | `Router`, `Application` | 4 |
| [nestjs](fixtures/nestjs/fixture.yaml) | TypeScript | `NestFactory`, `Injectable` | 4 |
| [spring-boot](fixtures/spring-boot/fixture.yaml) | Java | `SpringApplication`, `ApplicationContext` | 4 |
| [kafka](fixtures/kafka/fixture.yaml) | Java | `KafkaProducer`, `KafkaConsumer` | 4 |
| [gin](fixtures/gin/fixture.yaml) | Go | `Engine`, `RouterGroup` | 4 |
| [actix-web](fixtures/actix-web/fixture.yaml) | Rust | `HttpServer`, `App` | 4 |
| [aspnetcore](fixtures/aspnetcore/fixture.yaml) | C# | `WebApplication`, `WebApplicationBuilder` | 4 |

**Total: 40 cases** (30 REDACT + 10 PASS) across 8 languages.

## Scenarios

Each project has exactly 4 cases:

| Scenario | Expected | Description |
|----------|----------|-------------|
| `explain` | REDACT | Developer pastes a protected class and asks Claude Code to explain it |
| `use` | REDACT | Developer asks how to use a protected class in new code |
| `refactor` | REDACT | Developer asks to refactor existing code that calls a protected class |
| `pass` | PASS | Realistic prompt with **no** protected symbols — validates low false-positive rate |

## Running the benchmark

```bash
# From the repo root (requires kiri virtual environment):
python benchmarks/real-projects/runner.py

# Single project:
python benchmarks/real-projects/runner.py --project flask

# Verbose (prints every case including matched symbols):
python benchmarks/real-projects/runner.py --verbose
```

## Reproducing a case manually

If you have Kiri installed and running:

```bash
# 1. Register the project's protected symbols
kiri add @Flask @Scaffold

# 2. Inspect a prompt
kiri inspect --file benchmarks/real-projects/fixtures/flask/prompts/flask-001.txt

# Or inline:
kiri inspect "Can you explain how this Flask class works? class Flask(Scaffold): ..."
```

## Pipeline configuration

The runner uses the same `FilterPipeline` as production Kiri:

- **L2**: real `SymbolStore` populated from `protected_symbols` in the fixture
- **L1**: `_NullVectorStore` + `_NullEmbedder` — always scores `0.0` (no indexed files)
- **L3**: real `L3Filter` — fails open if Ollama is unavailable

This mirrors the scenario where a developer has registered explicit `@symbol`
entries in `.kiri/secrets` but has not yet indexed any source files.
L2 is therefore the deciding layer for all REDACT cases in this benchmark,
and L1/L3 are exercised (with zero score / fail-open respectively) to validate
the integration path.
