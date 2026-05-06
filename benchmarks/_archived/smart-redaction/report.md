# Smart Redaction Benchmark — Report v2

**Data:** 2026-04-02
**Casi valutati:** 10 (5 legal + 5 medical)
**Istruzioni:** claude_instructions.md v2 (task-aware redaction)
**Modello valutatore:** claude-sonnet-4-6

---

## Metriche Aggregate

| Metrica | v1 (uniform) | v2 (task-aware) | Delta | Target |
|---|---|---|---|---|
| Sensitive Coverage Rate | 1.00 | **1.00** | = | >= 0.90 |
| Utility Preservation Rate | 0.95 | **1.00** | **+0.05** | >= 0.85 |
| Over-Redaction Rate | 0% | **0%** | = | <= 10% |
| Full Protection Rate | 100% | **100%** | = | — |
| High-Risk Miss Rate | 0% | **0%** | = | 0% |

---

## Risultati per caso

| case_id | Domain | Task | Sensitivity | Coverage | Utility | Over-Red. | Note |
|---|---|---|---|---|---|---|---|
| L001 | legal | summary | high | 1.0 | 1.0 | false | — |
| L002 | legal | clause_extraction | high | 1.0 | 1.0 | false | — |
| L003 | legal | classification | medium | 1.0 | 1.0 | false | — |
| L004 | legal | rewrite | medium | 1.0 | 1.0 | false | — |
| L005 | legal | translation | high | 1.0 | 1.0 | false | — |
| M001 | medical | summary | high | 1.0 | 1.0 | false | Redazione completa |
| M002 | medical | triage_support | high | 1.0 | 1.0 | false | LAB_VALUE/THERAPY/DIAGNOSIS visibili by design |
| M003 | medical | letter_generation | medium | 1.0 | 1.0 | false | Redazione completa |
| M004 | medical | coding_support | medium | 1.0 | **1.0** ⬆ | false | DIAGNOSIS/VITAL_SIGN visibili by design |
| M005 | medical | translation | high | 1.0 | 1.0 | false | GENETIC_INFORMATION sempre redatto |

---

## Caso chiave: M004 (upgrade da 0.5 → 1.0)

### v1 — redazione uniforme
```
Input:    "polmonite batterica", "89%", "Policlinico Gemelli"
Redatto:  "[DIAGNOSIS]", "[VITAL_SIGN]", "[HOSPITAL]"
Utility:  0.5  — l'LLM non può suggerire il codice ICD-10 senza la diagnosi
```

### v2 — redazione task-aware
```
Input:    "polmonite batterica", "89%", "Policlinico Gemelli"
Redatto:  "polmonite batterica", "89%", "[HOSPITAL]"
Utility:  1.0  — l'LLM può codificare correttamente
Rationale: nessun identificativo diretto nel testo (no nome, no DOB, no cartella)
           → i dati clinici da soli non re-identificano il paziente
```

---

## Principio applicato: combinazione identificativa

Un dato clinico è protetto quando è **combinato** con un identificativo diretto.
Rimosso il nome/DOB/cartella, la diagnosi sola non ri-identifica il paziente
(salvo patologie estremamente rare — caso da gestire con soglia di rarità diagnostica, fuori scope v2).

```
PATIENT_NAME + DIAGNOSIS  →  dato personale sanitario  →  rediği tutto
[rimosso]    + DIAGNOSIS  →  dato clinico anonimo       →  visibile per task operativi
```

**Eccezione assoluta: GENETIC_INFORMATION**
Identificativo per definizione (DNA è unico), protetto sempre indipendentemente dal contesto.

---

## Calcolo metriche v2

```
Sensitive Coverage Rate    = 10/10 = 1.00
Utility Preservation Rate  = 10/10 = 1.00  (M004 ora 1.0)
Over-Redaction Rate        = 0/10  = 0%
Full Protection Rate       = 10/10 = 100%
High-Risk Miss Rate        = 0/6   = 0%    (casi HIGH: L001, L002, L005, M001, M002, M005)
```
