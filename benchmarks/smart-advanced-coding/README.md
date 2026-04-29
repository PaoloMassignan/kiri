# Coding Semantic Equivalence Benchmark Pack

Questo pacchetto contiene esempi di benchmark per validare che un refactoring generato da un LLM mantenga lo stesso comportamento del codice originale.

## Cosa misura
- equivalenza semantica
- preservazione dei test
- validità sintattica

## Come usarlo
1. Prendi `source_code`
2. Chiedi al modello di rifattorizzarlo secondo `task`
3. Salva il risultato come `model_output_code`
4. Dai a Claude:
   - sorgente originale
   - test
   - output rifattorizzato
5. Claude valuta se i test danno ancora gli stessi risultati

## Nota
Questo benchmark è pensato per casi di programmazione realistici:
- refactor di classi
- cleanup di funzioni
- semplificazione di query
- miglioramento naming
- refactor idiomatico
