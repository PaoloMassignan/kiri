# Advanced Semantic Equivalence Benchmark — Report

**Data:** 2026-04-03
**Runner:** advanced_benchmark_runner.py
**Strategia:** Python/C# con test reali | Java con compile check | altri con analisi statica

---

## Metriche Aggregate

| Metrica | Valore | Target |
|---|---|---|
| Semantic Equivalence Rate | **1.00** | >= 0.90 |
| Test Preservation Rate | **1.00** | >= 0.90 |
| Syntax Validity Rate | **1.00** | >= 0.95 |
| Broken Behavior Rate | **0%** | <= 10% |
| Test Failure Risk Rate | **0%** | <= 10% |

---

## Risultati per caso

| case_id | Language | Mode | Semantic | TestPreserv | Syntax | Stable |
|---|---|---|---|---|---|---|
| SE001 | python | real_tests | 1.0 | 1.0 | 1.0 | YES |
| SE002 | python | real_tests | 1.0 | 1.0 | 1.0 | YES |
| SE003 | javascript | static_analysis | 1.0 | 1.0 | 1.0 | YES |
| SE004 | typescript | static_analysis | 1.0 | 1.0 | 1.0 | YES |
| SE005 | java | compile_check | 1.0 | 1.0 | 1.0 | YES |
| SE006 | go | static_analysis | 1.0 | 1.0 | 1.0 | YES |
| SE007 | csharp | real_tests_dotnet | 1.0 | 1.0 | 1.0 | YES |
| SE008 | ruby | static_analysis | 1.0 | 1.0 | 1.0 | YES |
| SE009 | php | static_analysis | 1.0 | 1.0 | 1.0 | YES |
| SE010 | rust | static_analysis | 1.0 | 1.0 | 1.0 | YES |
| SE011 | sql | static_analysis | 1.0 | 1.0 | 1.0 | YES |
| SE012 | kotlin | static_analysis | 1.0 | 1.0 | 1.0 | YES |

---

## Modalita' di verifica per linguaggio

| Modalita' | Casi | Descrizione |
|---|---|---|
| real_tests | SE001, SE002 | Test Python eseguiti con unittest |
| real_tests_dotnet | SE007 | Test C# eseguiti con dotnet test + xUnit |
| compile_check | SE005 | Compilazione javac verificata |
| static_analysis | SE003, SE004, SE006, SE008, SE009, SE010, SE011, SE012 | Valutazione semantica per ispezione |

---

## Note sui refactoring

- **real_tests**: Test eseguiti realmente — risultato oggettivo.
- **real_tests_dotnet**: Test eseguiti realmente con xUnit — risultato oggettivo.
- **compile_check**: Compilazione verificata con javac. Equivalenza semantica confermata per ispezione (ternary = if-else).
- **static_analysis**: Runtime non disponibile. Score basato su analisi della struttura del codice e tabella di verita'.
