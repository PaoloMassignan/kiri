# Smart Redaction Benchmark Pack

Questo pacchetto contiene un benchmark iniziale per valutare uno smart redaction engine
su due domini:
- legale
- medico

## Obiettivo
Misurare quanto il sistema:
1. intercetta i contenuti sensibili
2. li sostituisce correttamente
3. preserva l'utilità del testo per il task richiesto

## File inclusi
- legal_redaction_dataset.json
- medical_redaction_dataset.json
- combined_redaction_dataset.csv
- claude_instructions.md
- evaluation_rubric.md
- results_template.csv

## Metriche consigliate
- Sensitive Coverage Rate
- Exact/Full Protection Rate
- Partial Redaction Rate
- Miss Rate
- Utility Preservation Score
- Over-Redaction Rate
