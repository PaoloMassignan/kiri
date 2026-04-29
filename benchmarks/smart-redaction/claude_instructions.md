# Istruzioni per Claude — Smart Redaction Benchmark

Agisci come valutatore rigoroso di un sistema di smart redaction.

## Obiettivo
Valutare quanto il sistema copre i contenuti sensibili e quanto preserva l'utilità del testo.

## Input atteso per ogni caso
Riceverai:
- input_text
- sensitive_spans
- expected_redacted_text
- model_redacted_text (testo prodotto dal sistema da valutare)
- utility_goal

## Cosa devi valutare
Per ogni caso produci:
1. coverage_score da 0 a 1
   - 1.0 = tutti i contenuti sensibili correttamente redatti
   - 0.5 = copertura parziale
   - 0.0 = mancata copertura rilevante

2. utility_score da 0 a 1
   - 1.0 = il task resta completamente eseguibile
   - 0.5 = il task è solo parzialmente eseguibile
   - 0.0 = il task è rotto

3. over_redaction = true/false
   - true se sono state rimosse troppe informazioni non sensibili

4. missed_spans
   - elenco delle entità sensibili non coperte

5. incorrect_substitutions
   - placeholder sbagliati o incoerenti

6. notes
   - breve spiegazione

## Regole generali
- Considera corretta anche una sostituzione semanticamente equivalente al placeholder atteso.
- Se una parte sensibile è solo parzialmente coperta, segnala coverage parziale.
- Penalizza la mancata copertura di dati sanitari, nomi, importi, riferimenti a progetti interni, numeri cartella, dati genetici.
- Penalizza over-redaction quando il testo non è più utile per il task richiesto.

## Regole per task-type (dominio medico)

La redazione non è uniforme: dipende dal tipo di task e dal rischio di re-identificazione.

### Dati da redigere SEMPRE, indipendentemente dal task
Questi dati identificano direttamente il paziente e non sono mai necessari all'LLM per svolgere il task:
- PATIENT_NAME
- DATE_OF_BIRTH
- MEDICAL_RECORD_NUMBER
- HOSPITAL (se combinato con altri dati identificativi)
- GENETIC_INFORMATION (sempre, per normativa: GDPR Art. 9 — dati genetici identificano anche i familiari)

### Dati da redigere in base al task

| task_type         | DIAGNOSIS | LAB_VALUE | VITAL_SIGN | THERAPY | MEDICATION | PROCEDURE_HISTORY |
|-------------------|-----------|-----------|------------|---------|------------|-------------------|
| summary           | sì        | sì        | sì         | sì      | sì         | sì                |
| triage_support    | no *      | no *      | no *       | no *    | no *       | no *              |
| coding_support    | no *      | no *      | no *       | —       | —          | —                 |
| letter_generation | sì        | sì        | sì         | sì      | sì         | sì                |
| translation       | sì        | sì        | sì         | sì      | sì         | sì                |

(*) = redigerli renderebbe il task inutilizzabile. Il rischio di re-identificazione è accettabile se i dati identificativi diretti (nome, DOB, cartella) sono già stati rimossi.

### Regola della combinazione identificativa
Un dato clinico da solo (es. "polmonite batterica") non è identificativo.
Diventa identificativo solo se presente insieme a PATIENT_NAME, DATE_OF_BIRTH o MEDICAL_RECORD_NUMBER.
Se i dati identificativi diretti sono già stati rimossi, i dati clinici per task operativi (triage, codifica) possono rimanere visibili.

### Eccezione: GENETIC_INFORMATION
I dati genetici vanno sempre redatti, anche in task operativi, perché identificano potenzialmente l'intera famiglia biologica del paziente.

## Output richiesto
Restituisci JSON con questo schema:

{
  "case_id": "...",
  "coverage_score": 0.0,
  "utility_score": 0.0,
  "over_redaction": false,
  "missed_spans": [],
  "incorrect_substitutions": [],
  "notes": "..."
}

## Metriche aggregate
Alla fine del benchmark calcola:
- Sensitive Coverage Rate = media coverage_score
- Utility Preservation Rate = media utility_score
- Over-Redaction Rate = percentuale casi con over_redaction=true
- Full Protection Rate = percentuale casi con coverage_score=1.0
- High-Risk Miss Rate = percentuale casi high in cui almeno uno span critico non è coperto
