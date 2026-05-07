# How to benchmark Kiri against your own codebase

This guide shows you how to create a benchmark fixture for your own proprietary
code and run it through the same evaluation pipeline we use for the 10 reference
projects.  The result is a reproducible F1 score that tells you exactly how well
Kiri protects your specific symbols — and where the gaps are.

---

## What you will produce

A single YAML file (`fixture.yaml`) and a one-line command.  The runner does
the rest: it indexes your source, runs every prompt through the full
FilterPipeline (L2 → L1 → L3), and prints precision, recall and F1 per
scenario and overall.

---

## Step 1 — Create the fixture directory

```
benchmarks/real-projects/fixtures/<your-project>/fixture.yaml
```

Copy the annotated template below into that file and fill in each section.

---

## The fixture format

```yaml
# ── Identity ───────────────────────────────────────────────────
project: my-platform          # short slug, no spaces
repo: internal://gitlab/...   # optional — shown in runner header
version: "2.1.0"
language: python              # python | java | typescript | go | rust | csharp | javascript

description: >
  One paragraph: what this component does and why it is proprietary.
  This is shown in the runner header and is your own documentation.

# ── Symbols to protect ─────────────────────────────────────────
#
# These are loaded into L2's SymbolStore and matched with word-boundary
# regex (\bSymbol\b).  Pick the class names, function names or module
# names that are most sensitive.  2-4 symbols per fixture is typical.
#
protected_symbols:
  - text: "CoreEngine"
    label: "CLASS_NAME"         # CLASS_NAME | FUNCTION_NAME | MODULE_NAME
  - text: "InternalRouter"
    label: "CLASS_NAME"

# ── Source files to index ──────────────────────────────────────
#
# Paste representative source code here.  The runner writes these files
# to a temp directory, chunks them with tree-sitter, embeds the chunks
# with all-MiniLM-L6-v2 (384-dim), and stores the vectors in an
# in-memory ChromaDB collection.
#
# Guidelines:
#   - 40–80 lines per file is ideal.  Longer files get truncated by the
#     model (max ~512 tokens ≈ 2 000 chars).
#   - Include the class definition, __init__ / constructor, and 2-3 key
#     methods.  That gives L1 enough signal to recognise the pattern even
#     when the class name is changed.
#   - Do NOT include generated code, auto-imports, or unrelated helpers.
#
source_files:
  - filename: "engine.py"       # filename drives tree-sitter language detection
    content: |
      class CoreEngine:
          def __init__(self, config: EngineConfig) -> None:
              self.config = config
              self._router = InternalRouter(config.routes)
              self._middleware: list[Middleware] = []

          def use(self, mw: Middleware) -> "CoreEngine":
              self._middleware.append(mw)
              return self

          def run(self, host: str = "127.0.0.1", port: int = 8080) -> None:
              for mw in self._middleware:
                  self._router.apply(mw)
              serve(self._router, host=host, port=port)

# ── Hard cases (L1 + L3 tested) ───────────────────────────────
#
# Prompts where the protected symbol does NOT appear verbatim.
# L2 is bypassed; L1 (semantic similarity) and L3 (Ollama classifier)
# must decide.  Write at least one of each scenario type.
#
# Three scenario types:
#
#   renamed_class        Same code, class name swapped.
#                        L1 should score > 0.75 (sim is high because
#                        field names, method bodies, internal calls match).
#                        Expected: L1 catches → REDACT.
#
#   partial_snippet      A method body pasted without the class definition.
#                        L1 recognises the pattern from the method structure.
#                        Expected: L1 catches → REDACT.
#
#   semantic_reformulation  Pure prose describing the code's behaviour —
#                        no code block, no internal API names.
#                        L1 often misses this.  Use it to document the gap.
#                        Expected: may be PASS (FN) — that is honest data.
#
# IMPORTANT: check for symbol leaks.
# If your renamed-class prompt still references a protected symbol inside
# the code body (e.g. self.router = InternalRouter(...)), L2 will catch it
# — not L1.  That is still a valid REDACT, but it tests a different thing.
# Note it in the description so the reader understands which layer fired.
#
hard_cases:
  - id: myplatform-h001
    scenario: renamed_class
    expected_action: REDACT
    expected_layer: L1
    description: "CoreEngine renamed to AppKernel — L2 misses, L1 catches via structural similarity"
    prompt: |
      I'm reviewing our internal AppKernel class and I don't understand why
      use() returns self instead of None. Can you explain the builder pattern
      and when run() actually binds the middleware chain?

      class AppKernel:
          def __init__(self, config: EngineConfig) -> None:
              self.config = config
              self._router = PlatformRouter(config.routes)
              self._middleware: list[Middleware] = []

          def use(self, mw: Middleware) -> "AppKernel":
              self._middleware.append(mw)
              return self

          def run(self, host: str = "127.0.0.1", port: int = 8080) -> None:
              for mw in self._middleware:
                  self._router.apply(mw)
              serve(self._router, host=host, port=port)

  - id: myplatform-h002
    scenario: partial_snippet
    expected_action: REDACT
    expected_layer: L1
    description: "run() body fragment without class context"
    prompt: |
      Why does this run method iterate middleware before calling serve()?
      Is there a reason the middleware is applied to the router at startup
      rather than at request time?

          for mw in self._middleware:
              self._router.apply(mw)
          serve(self._router, host=host, port=port)

  - id: myplatform-h003
    scenario: semantic_reformulation
    expected_action: REDACT
    expected_layer: L1
    description: "Prose description of engine/router pattern — L1 expected to miss; documents gap"
    prompt: |
      I'm building a platform where a central engine class holds a list of
      middleware and a router. Middleware is registered via a fluent builder
      and then applied to the router when the server starts. The server binds
      to a host and port supplied at runtime.

      Is there a cleaner way to handle middleware ordering when some middleware
      must run before routing and some after?

# ── Easy cases (L2 tested) ────────────────────────────────────
#
# Prompts where the protected symbol appears verbatim.
# L2 matches it with regex — no embedding, no Ollama.
# These should always produce F1 = 1.000.  If they don't, your symbol
# definition or L2 configuration has a problem.
#
# Four scenario types:
#
#   explain    Developer pastes protected code and asks Claude to explain it.
#   use        Developer asks how to use the protected class in new code.
#   refactor   Developer asks to modify existing code that calls the class.
#   pass       No protected symbols present — validates false-positive rate.
#              Must produce PASS, not REDACT.
#
cases:
  - id: myplatform-001
    scenario: explain
    expected_action: REDACT
    description: "Developer asks how CoreEngine initialises the router"
    prompt: |
      Can you explain how CoreEngine sets up InternalRouter and what happens
      if I call use() after run() has already been called?

      class CoreEngine:
          def __init__(self, config: EngineConfig) -> None:
              self._router = InternalRouter(config.routes)
              ...

  - id: myplatform-002
    scenario: use
    expected_action: REDACT
    description: "Developer asks how to add rate-limiting middleware to CoreEngine"
    prompt: |
      I need to add rate limiting to our CoreEngine before it goes to
      production.  How do I mount a RateLimitMiddleware so it runs before
      the InternalRouter dispatches the request?

      engine = CoreEngine(config)
      engine.use(AuthMiddleware(secret_key))
      engine.run(host="0.0.0.0", port=8080)

  - id: myplatform-003
    scenario: refactor
    expected_action: REDACT
    description: "Developer asks to extract CoreEngine setup into a factory function"
    prompt: |
      Refactor this so the CoreEngine and InternalRouter setup is in a
      dedicated factory function and main() only calls engine.run():

      def main():
          engine = CoreEngine(load_config())
          engine.use(LoggingMiddleware())
          engine.use(AuthMiddleware())
          engine.run()

  - id: myplatform-004
    scenario: pass
    expected_action: PASS
    description: "Developer asks about generic middleware pattern — no protected symbols"
    prompt: |
      What is the standard Python pattern for chaining callable middleware
      so each one wraps the next?  I want to implement it without any
      framework dependency.

      def apply_middleware(handler, middlewares):
          for mw in reversed(middlewares):
              handler = mw(handler)
          return handler
```

---

## Step 2 — Run the benchmark

From the repository root (activate the Kiri virtual environment first):

```bash
# Full run — both easy (L2) and hard (L1+L3) tiers:
python benchmarks/real-projects/runner.py --project my-platform

# Hard cases only — tests L1 and L3, requires Ollama running:
python benchmarks/real-projects/runner.py --project my-platform --hard-only

# Easy cases only — tests L2, no Ollama needed:
python benchmarks/real-projects/runner.py --project my-platform --easy-only

# Show every case with similarity scores:
python benchmarks/real-projects/runner.py --project my-platform --verbose
```

Ollama must be running for L3 to activate (`ollama serve`).  If it is
unavailable, L3 fails open — the grace-zone decision falls to L1's threshold
alone.

---

## Step 3 — Interpret the results

### Easy tier (cases)

```
Easy cases: 4 cases   TP=3  FP=0  FN=0  TN=1
Precision=1.000  Recall=1.000  F1=1.000
```

**F1 = 1.000 is expected.**  Every REDACT prompt contains the protected symbol
verbatim; every PASS prompt does not.  If F1 < 1.000 here, something is wrong
with the symbol definition — check the `protected_symbols` list and make sure
the text matches exactly (case-sensitive, word boundaries count).

### Hard tier (hard_cases)

```
Hard cases: 3 cases   TP=2  FP=0  FN=1  TN=0
Precision=1.000  Recall=0.667  F1=0.800
Scenarios:
  renamed_class           1/1  (100%)
  partial_snippet         1/1  (100%)
  semantic_reformulation  0/1    (0%)
```

**F1 < 1.000 is normal and informative.**  Each false negative (FN) documents
a genuine gap — a prompt type that bypasses Kiri's detection.

| sim score | What happened | Layer |
|-----------|---------------|-------|
| ≥ 0.90 | L1 redacted directly | L1 |
| 0.75 – 0.90 | L1 flagged, L3 (Ollama) confirmed | L1 + L3 |
| < 0.75 | L1 passed, never reached L3 | FN — gap |
| 0.000 | L2 caught it before L1 ran | L2 (check description) |

A `sim = 0.000` on a hard case means the prompt still contains a protected
symbol — check whether your renamed code leaks the original name through
internal API calls (e.g. `self.client = InternalRouter(...)`).

### What the numbers mean operationally

- **High easy-tier F1, lower hard-tier recall** is the normal and honest result.
  It means: "Kiri reliably catches direct references and structurally identical
  code.  It does not catch prose descriptions."
- **FP = 0** should always hold.  A false positive means Kiri blocked a
  legitimate prompt — check the PASS cases and your symbol list.
- **Hard-tier FN on `semantic_reformulation`** is expected.  That scenario
  documents where L1 runs out of signal.

---

## Tips for writing good cases

**Easy cases**
- Each REDACT case should mention the symbol in a natural way — not just as a
  class declaration.  Use it in `new MyClass()`, `MyClass.staticMethod()`, or
  as a type annotation.
- The PASS case should be a realistic question about the same domain but using
  only public/non-proprietary vocabulary.

**Hard cases — renamed_class**
- Rename the class but keep all internal method names, field names, and logic
  identical.  The structural signal is what L1 sees.
- Check for symbol leaks: if the renamed prompt still calls `InternalRouter()`
  or imports `my_module.CoreEngine`, L2 will intercept it — note this in the
  description.

**Hard cases — partial_snippet**
- Paste a method body (4–15 lines) without the class context.
- Choose a method with distinctive internal calls, not a trivial getter.

**Hard cases — semantic_reformulation**
- Write a paragraph that describes what the code does without naming the class
  or its internal methods.
- Expect this to fail (FN).  That is the point: it documents the boundary of
  what Kiri can detect.

**Source files**
- Keep each file under ~80 lines.  The embedding model truncates at ~512 tokens
  (~2 000 chars); long files produce weaker vectors.
- For Rust or other languages with verbose generic syntax, strip `where` bounds
  from the source — they consume tokens without adding semantic signal.
- Include at least the constructor and two non-trivial methods.  A struct with
  only field declarations scores poorly.
