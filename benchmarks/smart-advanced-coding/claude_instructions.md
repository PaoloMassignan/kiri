# Claude Instructions — Semantic Equivalence Benchmark for Code Refactoring

Agisci come valutatore rigoroso di refactoring code-to-code.

## Obiettivo
Per ogni caso devi verificare che il codice prodotto dopo la chiamata mantenga lo stesso comportamento del codice originale.

## Input del benchmark
Per ogni caso avrai:
- `task`
- `source_code`
- `tests`
- `expected_property`
- `model_output_code`

## Cosa devi valutare
Per ogni caso restituisci JSON con questo schema:

{
  "case_id": "...",
  "semantic_equivalence_score": 0.0,
  "test_preservation_score": 0.0,
  "syntax_validity_score": 0.0,
  "notes": "..."
}

## Criteri

### semantic_equivalence_score
- 1.0 = il comportamento appare invariato rispetto ai test e alla logica
- 0.5 = piccoli dubbi ma probabilmente equivalente
- 0.0 = comportamento cambiato o chiaramente non equivalente

### test_preservation_score
- 1.0 = tutti i test forniti dovrebbero ancora passare
- 0.5 = solo alcuni test passerebbero
- 0.0 = i test probabilmente fallirebbero

### syntax_validity_score
- 1.0 = codice sintatticamente coerente
- 0.5 = qualche problema minore
- 0.0 = codice rotto o non compilabile

## Metriche aggregate
Alla fine calcola:
- Semantic Equivalence Rate = media semantic_equivalence_score
- Test Preservation Rate = media test_preservation_score
- Syntax Validity Rate = media syntax_validity_score
- Broken Behavior Rate = percentuale casi con semantic_equivalence_score < 1.0
- Test Failure Risk Rate = percentuale casi con test_preservation_score < 1.0

## Regole importanti
- Valuta con priorità il fatto che i test continuino a dare gli stessi valori.
- Se il refactoring cambia naming ma non il comportamento, consideralo positivo.
- Se il refactoring introduce edge case diversi, penalizza.
- Se l'output non implementa più la stessa interfaccia pubblica, penalizza.
