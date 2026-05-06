# Evaluation Rubric — Smart Redaction

## 1. Sensitive Coverage Rate
Misura quanto il sistema copre gli span sensibili definiti nel dataset.

Formula:
coverage = span sensibili coperti correttamente / span sensibili totali

## 2. Utility Preservation Rate
Misura quanto il testo redatto conserva il compito originale.

Scala:
- 1.0 = task pienamente eseguibile
- 0.5 = task comprensibile ma degradato
- 0.0 = task compromesso

## 3. Over-Redaction Rate
Percentuale di casi in cui il sistema rimuove anche informazioni non sensibili necessarie al task.

## 4. Full Protection Rate
Percentuale di casi con copertura completa di tutti gli span sensibili.

## 5. High-Risk Miss Rate
Percentuale di casi ad alta sensibilità in cui almeno uno span critico rimane esposto.

## Soglie iniziali suggerite
- Sensitive Coverage Rate target: >= 0.90
- Utility Preservation Rate target: >= 0.85
- Over-Redaction Rate target: <= 0.10
- High-Risk Miss Rate target: <= 0.05
