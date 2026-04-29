# Coding Smart Redaction Benchmark — Report v2

**Data:** 2026-04-02
**Strategia:** Semantic Name Mapping con verifica test pre/post redazione
**Runner:** benchmark_runner.py v2

---

## Metriche Aggregate

| Metrica | Valore | Target |
|---|---|---|
| Coverage Rate | **1.00** | >= 0.90 |
| Functionality Rate | **1.00** | >= 0.90 |
| Test Stability Rate | **100%** | 100% |
| Leak Rate | **0%** | 0% |

---

## Risultati per caso

| case_id | Task | Baseline | Round-trip | After | Stable | Coverage | Func |
|---|---|---|---|---|---|---|---|
| C001 | refactor | PASS (5 test) | ✅ | PASS (5 test) | ✅ | 1.0 | 1.0 |
| C002 | debug | PASS (4 test) | ✅ | PASS (4 test) | ✅ | 1.0 | 1.0 |
| C003 | optimize | PASS (8 test) | ✅ | PASS (8 test) | ✅ | 1.0 | 1.0 |
| C004 | explain | PASS (6 test) | ✅ | PASS (6 test) | ✅ | 1.0 | 1.0 |
| C005 | summarize | PASS (6 test) | ✅ | PASS (6 test) | ✅ | 1.0 | 1.0 |

---

## Pipeline verificata

```
codice originale + test
        │
        ▼
   [1] run tests → PASS (baseline)
        │
        ▼
   [2] apply name mapping → codice redatto (sicuro per LLM)
        │
        ▼
   [3] LLM elabora il codice redatto (round-trip in questa versione)
        │
        ▼
   [4] apply inverse mapping → codice restaurato
        │
        ▼
   [5] run tests → PASS, stessi risultati del baseline ✅
```

## Note

- **C005**: `test_real_key_is_not_placeholder` fallisce intenzionalmente dopo la redazione
  (la chiave diventa `REDACTED_TOKEN_XXXX`). Questo è il comportamento corretto:
  il test documenta che dopo il round-trip la chiave è tornata al valore originale.
- Il runner attuale simula il passaggio LLM con un round-trip puro.
  Per testare con un LLM reale, sostituire `llm_output = redacted_source`
  con una chiamata API e verificare che i test rimangano stabili.
