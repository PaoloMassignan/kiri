# Comment Sanitization Benchmark — Report

**Data:** 2026-04-03
**Runner:** comment_benchmark_runner.py

---

## Metriche Aggregate

| Metrica | Valore | Target | Stato |
|---|---|---|---|
| Comment Coverage Rate | **1.00** | >= 0.92 | PASS |
| Comment Utility Rate | **1.00** | >= 0.80 | PASS |
| Code Integrity Rate | **1.00** | >= 0.98 | PASS |
| Comment Leak Rate | **0%** | <= 8% | PASS |
| Over-Removal Rate | **0%** | <= 15% | PASS |
| Full Comment Protection Rate | **100%** | — | — |
| High-Risk Comment Miss Rate | **0%** | <= 3% | PASS |

---

## Risultati per caso

| case_id | Language | Coverage | Utility | Integrity | Leak | Over-removal |
|---|---|---|---|---|---|---|
| CM001 | python | 1.0 | 1.0 | 1.0 | NO | NO |
| CM002 | javascript | 1.0 | 1.0 | 1.0 | NO | NO |
| CM003 | java | 1.0 | 1.0 | 1.0 | NO | NO |
| CM004 | typescript | 1.0 | 1.0 | 1.0 | NO | NO |
| CM005 | python | 1.0 | 1.0 | 1.0 | NO | NO |
| CM006 | go | 1.0 | 1.0 | 1.0 | NO | NO |
| CM007 | ruby | 1.0 | 1.0 | 1.0 | NO | NO |
| CM008 | csharp | 1.0 | 1.0 | 1.0 | NO | NO |
| CM009 | sql | 1.0 | 1.0 | 1.0 | NO | NO |
| CM010 | bash | 1.0 | 1.0 | 1.0 | NO | NO |

---

## Strategie di sanitizzazione per caso

- **CM001**: Generalizzazione: CLIENT_NAME e INTERNAL_PROJECT rimossi, INTERNAL_SYSTEM -> 'upstream dependency'
- **CM002**: Generalizzazione: CLIENT_NAME e ENVIRONMENT_INFO rimossi, INTERNAL_SERVICE -> 'fraud check service'
- **CM003**: Generalizzazione: CLIENT_NAME e LEGAL_EVENT rimossi, INTERNAL_LOGIC -> 'Threshold-based classification'
- **CM004**: Riscrittura docstring: tutti i 5 span rimossi, docstring riscritta genericamente
- **CM005**: Rimozione selettiva: riga SECURITY_BYPASS rimossa interamente; hint sui null preservato
- **CM006**: Sostituzione funzionale: commenti business sostituiti con descrizione neutra della funzione
- **CM007**: Generalizzazione TODO: CLIENT_NAME rimosso, CHANGE_EVENT generalizzato, INFRASTRUCTURE_DETAIL rimosso
- **CM008**: Strict mode: tutti i commenti rimossi (SECURITY_FINDING + PRIVILEGE_ESCALATION_HINT)
- **CM009**: Rimozione totale: commenti SQL rimossi, sostituiti con commento generico sul risultato
- **CM010**: Rimozione totale: entrambe le righe rimosse (node, datacenter, break-glass, incident response)
