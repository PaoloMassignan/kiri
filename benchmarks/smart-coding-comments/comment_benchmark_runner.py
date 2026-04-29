#!/usr/bin/env python3
"""
Comment Sanitization Benchmark Runner
======================================
Valuta la sanitizzazione di commenti e docstring nel codice.

Per ogni caso verifica:
  1. comment_coverage_score  - gli span sensibili sono stati rimossi/generalizzati?
  2. comment_utility_score   - i commenti rimasti sono ancora utili?
  3. code_integrity_score    - il codice (non i commenti) e' rimasto integro?
  4. comment_leak            - qualche span sensibile e' rimasto verbatim?
  5. over_removal            - e' stato rimosso troppo anche del non-sensibile?

Per Python: esegue anche la verifica sintattica (compile) del codice di output.
Per altri linguaggi: analisi strutturale dei commenti.

Uso:
  python comment_benchmark_runner.py
  python comment_benchmark_runner.py --show-diff
"""

import ast
import json
import re
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR    = Path(__file__).parent
DATASET     = BASE_DIR / "comment_sanitization_dataset_with_output.json"
RESULTS_OUT = BASE_DIR / "results.csv"
REPORT_OUT  = BASE_DIR / "report.md"
JSON_OUT    = BASE_DIR / "results.json"

# ---------------------------------------------------------------------------
# Helpers: estrazione commenti
# ---------------------------------------------------------------------------

COMMENT_PATTERNS = {
    "python":     [r"#[^\n]*", r'"""[\s\S]*?"""', r"'''[\s\S]*?'''"],
    "javascript": [r"//[^\n]*", r"/\*[\s\S]*?\*/"],
    "typescript": [r"//[^\n]*", r"/\*[\s\S]*?\*/"],
    "java":       [r"//[^\n]*", r"/\*[\s\S]*?\*/"],
    "go":         [r"//[^\n]*", r"/\*[\s\S]*?\*/"],
    "ruby":       [r"#[^\n]*"],
    "csharp":     [r"//[^\n]*", r"/\*[\s\S]*?\*/"],
    "sql":        [r"--[^\n]*", r"/\*[\s\S]*?\*/"],
    "bash":       [r"#[^\n]*"],
}

def extract_comments(code: str, language: str) -> list[str]:
    patterns = COMMENT_PATTERNS.get(language, [r"#[^\n]*", r"//[^\n]*"])
    comments = []
    for pat in patterns:
        comments.extend(re.findall(pat, code, re.DOTALL))
    return comments

def strip_comments(code: str, language: str) -> str:
    """Rimuove i commenti per estrarre solo il codice."""
    result = code
    patterns = COMMENT_PATTERNS.get(language, [r"#[^\n]*", r"//[^\n]*"])
    for pat in patterns:
        result = re.sub(pat, "", result, flags=re.DOTALL)
    return result

def normalize_code(code: str) -> str:
    """Rimuove whitespace extra per confronto strutturale."""
    return re.sub(r"\s+", " ", code).strip()

# ---------------------------------------------------------------------------
# Verifica sintattica Python
# ---------------------------------------------------------------------------

def check_python_syntax(code: str) -> tuple[bool, str]:
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as e:
        return False, str(e)

# ---------------------------------------------------------------------------
# Valutazione singolo caso
# ---------------------------------------------------------------------------

def evaluate_case(case: dict, show_diff: bool = False) -> dict:
    cid      = case["id"]
    language = case["language"]
    input_code  = case["input_code"]
    output_code = case["model_output_code"]
    spans    = case["sensitive_comment_spans"]

    # --- Estrai commenti da input e output ---
    input_comments  = extract_comments(input_code,  language)
    output_comments = extract_comments(output_code, language)

    input_comments_text  = " ".join(input_comments).lower()
    output_comments_text = " ".join(output_comments).lower()

    # --- 1. comment_coverage_score ---
    # Conta quanti span sensibili sono stati rimossi o generalizzati
    leaked_spans   = []
    covered_spans  = []

    for span in spans:
        token = span["text"].lower()
        if token in output_comments_text:
            leaked_spans.append(span["text"])
        else:
            covered_spans.append(span["text"])

    total_spans = len(spans)
    if total_spans == 0:
        coverage = 1.0
    elif len(leaked_spans) == 0:
        coverage = 1.0
    elif len(covered_spans) == 0:
        coverage = 0.0
    else:
        coverage = round(len(covered_spans) / total_spans, 2)

    # --- 2. comment_leak ---
    comment_leak = len(leaked_spans) > 0

    # --- 3. comment_utility_score ---
    # Ha preservato qualche commento tecnico generico?
    # Semplice euristica: se c'e' almeno un commento nell'output e non e' solo whitespace
    has_output_comments = any(c.strip().lstrip("#/- *").strip() for c in output_comments)

    # Se l'input aveva commenti e l'output non ne ha: potrebbe essere over-removal o scelta corretta
    # Distinguiamo: se la policy e' "strict" accettiamo rimozione totale
    strict_mode = "strict" in case.get("expected_comment_policy", "").lower() or \
                  language in ("bash",) or \
                  any(s["label"] in ("SECURITY_FINDING", "SECURITY_BYPASS", "PRIVILEGE_ESCALATION_HINT")
                      for s in spans)

    if has_output_comments:
        # Commenti presenti — verifica che siano genuinamente utili (non vuoti)
        meaningful_comments = [
            c for c in output_comments
            if len(c.strip().lstrip("#/- *").strip()) > 5
        ]
        utility = 1.0 if meaningful_comments else 0.5
    elif strict_mode:
        # Rimozione totale accettabile in strict mode
        utility = 1.0
    else:
        # Nessun commento rimasto in modalita' non-strict: utility degradata
        utility = 0.5

    # --- 4. code_integrity_score ---
    # Confronta il codice senza commenti tra input e output
    input_stripped  = normalize_code(strip_comments(input_code,  language))
    output_stripped = normalize_code(strip_comments(output_code, language))
    code_identical  = input_stripped == output_stripped

    if language == "python":
        syntax_ok, syntax_err = check_python_syntax(output_code)
        if not syntax_ok:
            integrity = 0.0
            integrity_note = f"SyntaxError: {syntax_err}"
        elif code_identical:
            integrity = 1.0
            integrity_note = "code body identical"
        else:
            integrity = 0.8
            integrity_note = "minor code differences (whitespace/formatting)"
    else:
        integrity = 1.0 if code_identical else 0.8
        integrity_note = "code body identical" if code_identical else "minor differences"

    # --- 5. over_removal ---
    # Ha rimosso commenti NON sensibili che erano utili?
    # Euristica: conta le righe di commento originali vs output
    input_comment_lines  = len([c for c in input_comments  if c.strip().lstrip("#/- *").strip()])
    output_comment_lines = len([c for c in output_comments if c.strip().lstrip("#/- *").strip()])

    # Over-removal se: non strict, c'erano commenti non-sensibili utili, sono stati rimossi tutti
    non_sensitive_comments_existed = input_comment_lines > len(spans)
    all_removed = output_comment_lines == 0
    over_removal = (not strict_mode) and non_sensitive_comments_existed and all_removed

    if show_diff:
        print(f"\n  Input comments  : {input_comments}")
        print(f"  Output comments : {output_comments}")
        print(f"  Leaked spans    : {leaked_spans}")
        print(f"  Code identical  : {code_identical}")

    return {
        "case_id":                 cid,
        "language":                language,
        "comment_coverage_score":  coverage,
        "comment_utility_score":   utility,
        "code_integrity_score":    integrity,
        "over_removal":            over_removal,
        "comment_leak":            comment_leak,
        "missed_comment_elements": leaked_spans,
        "notes": (
            f"covered={len(covered_spans)}/{total_spans} spans | "
            f"leak={comment_leak} | "
            f"integrity={integrity_note} | "
            f"strict_mode={strict_mode}"
        ),
    }

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    show_diff = "--show-diff" in sys.argv

    print("=" * 62)
    print("  Comment Sanitization Benchmark Runner")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 62)

    with open(DATASET, encoding="utf-8") as f:
        dataset = json.load(f)

    results = []
    for case in dataset:
        print(f"\n>>  {case['id']}  [{case['language']}]")
        r = evaluate_case(case, show_diff=show_diff)
        results.append(r)

        cov  = r["comment_coverage_score"]
        util = r["comment_utility_score"]
        intg = r["code_integrity_score"]
        leak = r["comment_leak"]
        over = r["over_removal"]
        print(f"   Coverage : {cov:.1f}  |  Utility: {util:.1f}  |  Integrity: {intg:.1f}")
        print(f"   Leak     : {'YES [!!]' if leak else 'NO  [OK]'}  |  Over-removal: {'YES' if over else 'NO'}")
        if r["missed_comment_elements"]:
            print(f"   Missed   : {r['missed_comment_elements']}")

    # -----------------------------------------------------------------------
    # Metriche aggregate
    # -----------------------------------------------------------------------
    n = len(results)
    coverage_rate  = sum(r["comment_coverage_score"]  for r in results) / n
    utility_rate   = sum(r["comment_utility_score"]   for r in results) / n
    integrity_rate = sum(r["code_integrity_score"]    for r in results) / n
    leak_rate      = sum(1 for r in results if r["comment_leak"])    / n
    over_rate      = sum(1 for r in results if r["over_removal"])    / n
    full_prot_rate = sum(1 for r in results if r["comment_coverage_score"] == 1.0) / n

    # High-risk: SECURITY_*, CLIENT_*, INTERNAL_* labels
    HIGH_RISK_LABELS = {
        "SECURITY_BYPASS", "SECURITY_FINDING", "SECURITY_PROCEDURE", "SECURITY_CONTEXT",
        "PRIVILEGE_ESCALATION_HINT", "CLIENT_NAME", "CLIENT_TYPE",
        "INTERNAL_SYSTEM", "INTERNAL_PIPELINE", "INTERNAL_BRIDGE",
        "INTERNAL_ENDPOINT", "INTERNAL_NODE", "INTERNAL_TEAM",
    }
    high_risk_cases = [
        c for c in dataset
        if any(s["label"] in HIGH_RISK_LABELS for s in c["sensitive_comment_spans"])
    ]
    high_risk_miss = sum(
        1 for c in high_risk_cases
        for r in results
        if r["case_id"] == c["id"] and r["comment_leak"]
    ) / max(len(high_risk_cases), 1)

    print("\n" + "=" * 62)
    print("  METRICHE AGGREGATE")
    print("=" * 62)
    print(f"  Comment Coverage Rate        : {coverage_rate:.2f}   (target >= 0.92)")
    print(f"  Comment Utility Rate         : {utility_rate:.2f}   (target >= 0.80)")
    print(f"  Code Integrity Rate          : {integrity_rate:.2f}   (target >= 0.98)")
    print(f"  Comment Leak Rate            : {leak_rate:.0%}   (target <= 8%)")
    print(f"  Over-Removal Rate            : {over_rate:.0%}   (target <= 15%)")
    print(f"  Full Comment Protection Rate : {full_prot_rate:.0%}")
    print(f"  High-Risk Comment Miss Rate  : {high_risk_miss:.0%}   (target <= 3%)")

    summary = {
        "run_at":                       datetime.now().isoformat(),
        "cases_total":                  n,
        "comment_coverage_rate":        round(coverage_rate,  4),
        "comment_utility_rate":         round(utility_rate,   4),
        "code_integrity_rate":          round(integrity_rate, 4),
        "comment_leak_rate":            round(leak_rate,      4),
        "over_removal_rate":            round(over_rate,      4),
        "full_comment_protection_rate": round(full_prot_rate, 4),
        "high_risk_comment_miss_rate":  round(high_risk_miss, 4),
    }

    # -----------------------------------------------------------------------
    # Salva JSON
    # -----------------------------------------------------------------------
    with open(JSON_OUT, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "cases": results}, f, indent=2, ensure_ascii=False)
    print(f"\n  Risultati JSON  -> {JSON_OUT.name}")

    # -----------------------------------------------------------------------
    # Salva CSV
    # -----------------------------------------------------------------------
    with open(RESULTS_OUT, "w", encoding="utf-8") as f:
        f.write("case_id,language,comment_coverage_score,comment_utility_score,"
                "code_integrity_score,over_removal,comment_leak,missed_comment_elements,notes\n")
        for r in results:
            missed = "|".join(r["missed_comment_elements"])
            notes  = r["notes"].replace(",", ";")
            f.write(
                f"{r['case_id']},{r['language']},"
                f"{r['comment_coverage_score']},{r['comment_utility_score']},"
                f"{r['code_integrity_score']},{r['over_removal']},{r['comment_leak']},"
                f"\"{missed}\",\"{notes}\"\n"
            )
    print(f"  Risultati CSV   -> {RESULTS_OUT.name}")

    # -----------------------------------------------------------------------
    # Genera report Markdown
    # -----------------------------------------------------------------------
    _write_report(summary, results)
    print(f"  Report Markdown -> {REPORT_OUT.name}\n")


def _write_report(summary: dict, results: list):
    lines = [
        "# Comment Sanitization Benchmark — Report",
        "",
        f"**Data:** {summary['run_at'][:10]}",
        f"**Runner:** comment_benchmark_runner.py",
        "",
        "---",
        "",
        "## Metriche Aggregate",
        "",
        "| Metrica | Valore | Target | Stato |",
        "|---|---|---|---|",
        f"| Comment Coverage Rate | **{summary['comment_coverage_rate']:.2f}** | >= 0.92 | {'PASS' if summary['comment_coverage_rate'] >= 0.92 else 'FAIL'} |",
        f"| Comment Utility Rate | **{summary['comment_utility_rate']:.2f}** | >= 0.80 | {'PASS' if summary['comment_utility_rate'] >= 0.80 else 'FAIL'} |",
        f"| Code Integrity Rate | **{summary['code_integrity_rate']:.2f}** | >= 0.98 | {'PASS' if summary['code_integrity_rate'] >= 0.98 else 'FAIL'} |",
        f"| Comment Leak Rate | **{summary['comment_leak_rate']:.0%}** | <= 8% | {'PASS' if summary['comment_leak_rate'] <= 0.08 else 'FAIL'} |",
        f"| Over-Removal Rate | **{summary['over_removal_rate']:.0%}** | <= 15% | {'PASS' if summary['over_removal_rate'] <= 0.15 else 'FAIL'} |",
        f"| Full Comment Protection Rate | **{summary['full_comment_protection_rate']:.0%}** | — | — |",
        f"| High-Risk Comment Miss Rate | **{summary['high_risk_comment_miss_rate']:.0%}** | <= 3% | {'PASS' if summary['high_risk_comment_miss_rate'] <= 0.03 else 'FAIL'} |",
        "",
        "---",
        "",
        "## Risultati per caso",
        "",
        "| case_id | Language | Coverage | Utility | Integrity | Leak | Over-removal |",
        "|---|---|---|---|---|---|---|",
    ]

    for r in results:
        lines.append(
            f"| {r['case_id']} | {r['language']} "
            f"| {r['comment_coverage_score']:.1f} "
            f"| {r['comment_utility_score']:.1f} "
            f"| {r['code_integrity_score']:.1f} "
            f"| {'YES' if r['comment_leak'] else 'NO'} "
            f"| {'YES' if r['over_removal'] else 'NO'} |"
        )

    lines += [
        "",
        "---",
        "",
        "## Strategie di sanitizzazione per caso",
        "",
    ]

    strategies = {
        "CM001": "Generalizzazione: CLIENT_NAME e INTERNAL_PROJECT rimossi, INTERNAL_SYSTEM -> 'upstream dependency'",
        "CM002": "Generalizzazione: CLIENT_NAME e ENVIRONMENT_INFO rimossi, INTERNAL_SERVICE -> 'fraud check service'",
        "CM003": "Generalizzazione: CLIENT_NAME e LEGAL_EVENT rimossi, INTERNAL_LOGIC -> 'Threshold-based classification'",
        "CM004": "Riscrittura docstring: tutti i 5 span rimossi, docstring riscritta genericamente",
        "CM005": "Rimozione selettiva: riga SECURITY_BYPASS rimossa interamente; hint sui null preservato",
        "CM006": "Sostituzione funzionale: commenti business sostituiti con descrizione neutra della funzione",
        "CM007": "Generalizzazione TODO: CLIENT_NAME rimosso, CHANGE_EVENT generalizzato, INFRASTRUCTURE_DETAIL rimosso",
        "CM008": "Strict mode: tutti i commenti rimossi (SECURITY_FINDING + PRIVILEGE_ESCALATION_HINT)",
        "CM009": "Rimozione totale: commenti SQL rimossi, sostituiti con commento generico sul risultato",
        "CM010": "Rimozione totale: entrambe le righe rimosse (node, datacenter, break-glass, incident response)",
    }

    for cid, strategy in strategies.items():
        lines.append(f"- **{cid}**: {strategy}")

    with open(REPORT_OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
