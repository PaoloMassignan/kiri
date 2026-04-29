# Quickstart Guide

## Prerequisites

### Software

| Component | Minimum | Notes |
|-----------|---------|-------|
| Docker | 24.0+ | Docker Compose v2 included |
| Docker Compose | 2.20+ | Bundled with Docker Desktop |
| Python | 3.11+ | Local install only — not needed with Docker |

Ollama is **bundled inside the Docker image** — you do not install it separately.
For local (non-Docker) installs, Ollama is optional: the gateway degrades gracefully
to L1+L2 only if L3 is unavailable.

### Hardware

| Configuration | RAM | Disk | CPU |
|---------------|-----|------|-----|
| L1+L2 only (no Ollama) | 512 MB | 500 MB | any |
| Full stack (L1+L2+L3) — CPU inference | 4 GB | 3 GB | 2+ cores |
| Full stack — GPU inference | 6 GB system + 2 GB VRAM | 3 GB | 2+ cores |

**Disk breakdown:**
- Embedding model (`all-MiniLM-L6-v2`): ~90 MB
- Ollama L3 classifier (`qwen2.5:3b`): ~2.0 GB
- Vector index (ChromaDB): grows with codebase, typically < 100 MB

**GPU is optional.** `qwen2.5:3b` on a modern 4-core CPU classifies a prompt
in ~1–2 seconds — fast enough for interactive use. A GPU (CUDA or Metal) brings
this under 200 ms. The L1 vector search and L2 symbol match are always fast
regardless of GPU.

**Tested on:** Apple M-series (macOS), Intel/AMD x86-64 (Linux, Windows with
WSL2 or Docker Desktop). ARM64 Linux is supported via the `linux/arm64` Docker
manifest.

---

## Hello World — per language

All nine supported languages follow the same workflow:

```
kiri add <file>          # mark it protected
kiri inspect "<snippet>" # verify the filter fires
```

Replace `gateway` with `docker compose exec gateway gateway` if using Docker.

---

### Python

```python
# pricing.py
_DEMAND_EXPONENT = 1.7   # validated on Q3 2024 A/B test

def compute_price(base: float, demand: float) -> float:
    return round(base * demand ** _DEMAND_EXPONENT, 2)
```

```bash
kiri add pricing.py
kiri inspect "def compute_price(base, demand):
    return round(base * demand ** 1.7, 2)"
```

```
Decision : REDACT
Symbols  : compute_price, _DEMAND_EXPONENT, 1.7
```

---

### JavaScript

```javascript
// pricing.js
const DEMAND_EXPONENT = 1.7; // validated on Q3 2024 A/B test

function computePrice(base, demand) {
    return Math.round(base * Math.pow(demand, DEMAND_EXPONENT) * 100) / 100;
}
```

```bash
kiri add pricing.js
kiri inspect "function computePrice(base, demand) {
    return Math.round(base * Math.pow(demand, 1.7) * 100) / 100;
}"
```

```
Decision : REDACT
Symbols  : computePrice, DEMAND_EXPONENT, 1.7
```

---

### TypeScript

```typescript
// pricing.ts
const DEMAND_EXPONENT = 1.7; // validated on Q3 2024 A/B test

function computePrice(base: number, demand: number): number {
    return Math.round(base * Math.pow(demand, DEMAND_EXPONENT) * 100) / 100;
}
```

```bash
kiri add pricing.ts
kiri inspect "function computePrice(base: number, demand: number): number {
    return Math.round(base * Math.pow(demand, 1.7) * 100) / 100;
}"
```

```
Decision : REDACT
Symbols  : computePrice, DEMAND_EXPONENT, 1.7
```

---

### Java

```java
// PricingEngine.java
public class PricingEngine {
    private static final double DEMAND_EXPONENT = 1.7; // Q3 2024 A/B test

    public double computePrice(double base, double demand) {
        return Math.round(base * Math.pow(demand, DEMAND_EXPONENT) * 100.0) / 100.0;
    }
}
```

```bash
kiri add PricingEngine.java
kiri inspect "public double computePrice(double base, double demand) {
    return Math.round(base * Math.pow(demand, 1.7) * 100.0) / 100.0;
}"
```

```
Decision : REDACT
Symbols  : computePrice, DEMAND_EXPONENT, 1.7
```

---

### Go

```go
// pricing.go
package pricing

import "math"

const demandExponent = 1.7 // validated on Q3 2024 A/B test

func ComputePrice(base, demand float64) float64 {
    return math.Round(base*math.Pow(demand, demandExponent)*100) / 100
}
```

```bash
kiri add pricing.go
kiri inspect "func ComputePrice(base, demand float64) float64 {
    return math.Round(base*math.Pow(demand, 1.7)*100) / 100
}"
```

```
Decision : REDACT
Symbols  : ComputePrice, demandExponent, 1.7
```

---

### Rust

```rust
// pricing.rs
const DEMAND_EXPONENT: f64 = 1.7; // validated on Q3 2024 A/B test

fn compute_price(base: f64, demand: f64) -> f64 {
    (base * demand.powf(DEMAND_EXPONENT) * 100.0).round() / 100.0
}
```

```bash
kiri add pricing.rs
kiri inspect "fn compute_price(base: f64, demand: f64) -> f64 {
    (base * demand.powf(1.7) * 100.0).round() / 100.0
}"
```

```
Decision : REDACT
Symbols  : compute_price, DEMAND_EXPONENT, 1.7
```

---

### C

```c
/* pricing.c */
#define DEMAND_EXPONENT 1.7  /* validated on Q3 2024 A/B test */

double compute_price(double base, double demand) {
    return round(base * pow(demand, DEMAND_EXPONENT) * 100.0) / 100.0;
}
```

```bash
kiri add pricing.c
kiri inspect "double compute_price(double base, double demand) {
    return round(base * pow(demand, 1.7) * 100.0) / 100.0;
}"
```

```
Decision : REDACT
Symbols  : compute_price, DEMAND_EXPONENT, 1.7
```

---

### C++

```cpp
// pricing.cpp
constexpr double DEMAND_EXPONENT = 1.7; // validated on Q3 2024 A/B test

double computePrice(double base, double demand) {
    return std::round(base * std::pow(demand, DEMAND_EXPONENT) * 100.0) / 100.0;
}
```

```bash
kiri add pricing.cpp
kiri inspect "double computePrice(double base, double demand) {
    return std::round(base * std::pow(demand, 1.7) * 100.0) / 100.0;
}"
```

```
Decision : REDACT
Symbols  : computePrice, DEMAND_EXPONENT, 1.7
```

---

### C#

```csharp
// PricingEngine.cs
public class PricingEngine {
    private const double DemandExponent = 1.7; // validated on Q3 2024 A/B test

    public double ComputePrice(double basePrice, double demand) {
        return Math.Round(basePrice * Math.Pow(demand, DemandExponent) * 100.0) / 100.0;
    }
}
```

```bash
kiri add PricingEngine.cs
kiri inspect "public double ComputePrice(double basePrice, double demand) {
    return Math.Round(basePrice * Math.Pow(demand, 1.7) * 100.0) / 100.0;
}"
```

```
Decision : REDACT
Symbols  : ComputePrice, DemandExponent, 1.7
```

---

## What REDACT looks like to the LLM

When the gateway forwards a redacted prompt, protected function bodies are
replaced with a safe stub. The LLM sees the function signature and a
purpose summary — enough to help with the surrounding code, but without
any implementation detail:

```python
# Original (never leaves your network):
def compute_price(base: float, demand: float) -> float:
    return round(base * demand ** 1.7, 2)

# What the LLM receives:
def compute_price(base: float, demand: float) -> float:
    # [PROTECTED] compute_price
    # Purpose: Computes the final price given a base price and demand index.
    # Parameters: base (float), demand (float). Returns: float.
    ...
```

The same stub format applies to all languages — Java, Go, Rust etc. use
`// [PROTECTED]` instead of `#`.

---

## Troubleshooting

**`kiri add` returns "Path does not exist"**

Make sure you run from your project root, or pass the full absolute path.
When using Docker:

```bash
# Works from any directory:
docker compose exec gateway kiri add test_project/pricing.py

# If still failing, use absolute path inside the container:
docker compose exec gateway kiri add /workspace/test_project/pricing.py
```

**`kiri inspect` returns PASS for code I expected to BLOCK**

The file must be indexed before the filter activates. Confirm with:

```bash
kiri status
# If "Indexed chunks: 0", the server may not have indexed yet:
kiri index pricing.py
```

**L3 (Ollama) not running — only L1+L2 active**

Check Ollama is healthy:

```bash
docker compose ps       # should show ollama as healthy
docker compose logs ollama --tail 20
```

The gateway continues to protect with L1+L2 even when Ollama is unavailable.
L2 (symbol match) is always active and never degrades.
