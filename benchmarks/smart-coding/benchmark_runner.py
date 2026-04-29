#!/usr/bin/env python3
"""
Coding Smart Redaction Benchmark Runner v2
==========================================
Verifica che il codice compili e i test passino prima e dopo la redazione.

Pipeline per ogni caso:
  1. Esegui test su codice originale  → baseline (deve PASS)
  2. Applica name mapping a codice + test  → versione redatta (sicura per LLM)
  3. [Opzionale] Passa il codice redatto all'LLM per il task richiesto
  4. Applica mapping inverso al codice restituito dall'LLM  → codice restaurato
  5. Esegui test su codice restaurato  → deve PASS con stessi risultati del baseline

Uso:
  python benchmark_runner.py                  # round-trip puro (no LLM)
  python benchmark_runner.py --show-code      # mostra il codice redatto per ogni caso
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

BASE_DIR    = Path(__file__).parent
DATASET     = BASE_DIR / "coding_dataset_v2.json"
MAPPING     = BASE_DIR / "name_mapping.json"
RESULTS_OUT = BASE_DIR / "results_v2.json"
REPORT_OUT  = BASE_DIR / "report_v2.md"


# ---------------------------------------------------------------------------
# Name mapping
# ---------------------------------------------------------------------------

def apply_mapping(text: str, mappings: list[dict], reverse: bool = False) -> str:
    """
    Sostituisce i token sensibili nel testo.
    - reverse=False  → redazione   (original → replacement)
    - reverse=True   → de-redazione (replacement → original)
    Ordina per lunghezza decrescente per evitare sostituzioni parziali.
    """
    pairs = [(m["original"], m["replacement"]) for m in mappings]
    if reverse:
        pairs = [(r, o) for o, r in pairs]
    pairs.sort(key=lambda x: len(x[0]), reverse=True)
    for src, dst in pairs:
        text = text.replace(src, dst)
    return text


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

def run_tests(source_code: str, test_code: str, label: str) -> dict:
    """
    Scrive source + test in una directory temporanea ed esegue unittest.
    Restituisce un dict con: passed, test_count, failures, errors, output.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path  = os.path.join(tmpdir, "module.py")
        test_path = os.path.join(tmpdir, "test_module.py")

        with open(src_path, "w", encoding="utf-8") as f:
            f.write(source_code)

        # Il test importa tutto dal modulo nella stessa directory
        full_test = (
            "import sys, os\n"
            "sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n"
            "from module import *\n\n"
            + test_code
        )
        with open(test_path, "w", encoding="utf-8") as f:
            f.write(full_test)

        proc = subprocess.run(
            [sys.executable, "-m", "unittest", "test_module", "-v"],
            capture_output=True, text=True, cwd=tmpdir, timeout=30
        )

    # unittest scrive su stderr
    output = proc.stderr + proc.stdout
    passed = proc.returncode == 0

    # Estrai conteggi dalla riga finale  es: "Ran 5 tests in 0.001s"
    ran_match = re.search(r"Ran (\d+) test", output)
    test_count = int(ran_match.group(1)) if ran_match else 0

    fail_match = re.search(r"failures=(\d+)", output)
    err_match  = re.search(r"errors=(\d+)", output)
    failures   = int(fail_match.group(1)) if fail_match else 0
    errors     = int(err_match.group(1))  if err_match  else 0

    return {
        "label":      label,
        "passed":     passed,
        "test_count": test_count,
        "failures":   failures,
        "errors":     errors,
        "output":     output.strip(),
    }


# ---------------------------------------------------------------------------
# Single case
# ---------------------------------------------------------------------------

def run_case(case: dict, all_mappings: list[dict], show_code: bool = False) -> dict:
    case_id  = case["id"]
    language = case["language"]

    result = {
        "case_id":  case_id,
        "language": language,
        "task":     case["task"],
    }

    if language != "python":
        result["skipped"] = True
        result["reason"]  = f"Language '{language}' not supported by runner (only Python)"
        return result

    # Mappings specifici per questo caso
    case_maps = [m for m in all_mappings if m.get("case_id") == case_id]

    source = case["source_code"]
    tests  = case["test_code"]

    # ------------------------------------------------------------------
    # Step 1 — Baseline: esegui originale
    # ------------------------------------------------------------------
    baseline = run_tests(source, tests, "baseline")
    result["baseline"] = baseline

    if not baseline["passed"]:
        result["error"] = "Baseline tests FAIL — il codice originale è rotto, benchmark non valido."
        result["coverage_score"]        = 0.0
        result["functionality_preserved"] = 0.0
        result["security_leak"]         = True
        result["tests_stable"]          = False
        return result

    # ------------------------------------------------------------------
    # Step 2 — Redazione: applica name mapping a codice e test
    # ------------------------------------------------------------------
    redacted_source = apply_mapping(source, case_maps)
    redacted_tests  = apply_mapping(tests,  case_maps)

    result["redacted_source"] = redacted_source
    result["redacted_tests"]  = redacted_tests

    if show_code:
        print(f"\n  {'─'*50}")
        print(f"  Codice redatto ({case_id}):")
        for line in redacted_source.splitlines():
            print(f"    {line}")

    # Verifica che la redazione abbia effettivamente modificato qualcosa
    actually_redacted = redacted_source != source
    result["actually_redacted"] = actually_redacted

    # ------------------------------------------------------------------
    # Step 3 — Simulazione LLM (round-trip puro)
    # In produzione: qui si chiama l'LLM con redacted_source.
    # Il runner verifica il contratto: se l'LLM restituisce codice
    # strutturalmente equivalente, il de-mapping deve produrre codice
    # che fa passare i test originali.
    # ------------------------------------------------------------------
    llm_output = redacted_source  # round-trip: nessuna trasformazione LLM

    # ------------------------------------------------------------------
    # Step 4 — De-redazione: mapping inverso
    # ------------------------------------------------------------------
    restored_source = apply_mapping(llm_output,      case_maps, reverse=True)
    restored_tests  = apply_mapping(redacted_tests,  case_maps, reverse=True)

    result["round_trip_clean"] = (restored_source == source)
    result["restored_source"]  = restored_source

    # ------------------------------------------------------------------
    # Step 5 — Verifica post-round-trip
    # ------------------------------------------------------------------
    after = run_tests(restored_source, restored_tests, "after_round_trip")
    result["after_round_trip"] = after

    # ------------------------------------------------------------------
    # Metriche
    # ------------------------------------------------------------------
    tests_stable = (
        baseline["passed"]   == after["passed"] and
        baseline["test_count"] == after["test_count"] and
        baseline["failures"] == after["failures"] and
        baseline["errors"]   == after["errors"]
    )
    result["tests_stable"]            = tests_stable
    result["coverage_score"]          = 1.0 if actually_redacted else 0.0
    result["functionality_preserved"] = 1.0 if tests_stable and after["passed"] else 0.0
    result["security_leak"]           = not result["round_trip_clean"]

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    show_code = "--show-code" in sys.argv

    print("=" * 62)
    print("  Coding Smart Redaction Benchmark Runner v2")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 62)

    with open(DATASET, encoding="utf-8") as f:
        dataset = json.load(f)
    with open(MAPPING, encoding="utf-8") as f:
        mapping_data = json.load(f)
    all_mappings = mapping_data["mappings"]

    results = []
    for case in dataset:
        print(f"\n>>  {case['id']}  [{case['task']}]  ({case['language']})")
        r = run_case(case, all_mappings, show_code=show_code)
        results.append(r)

        if r.get("skipped"):
            print(f"   ⏭  Skipped: {r['reason']}")
            continue

        if r.get("error"):
            print(f"   ❌  {r['error']}")
            continue

        bl = r["baseline"]
        af = r["after_round_trip"]

        print(f"   Baseline         : {'✅ PASS' if bl['passed'] else '❌ FAIL'}  "
              f"({bl['test_count']} tests, {bl['failures']} fail, {bl['errors']} err)")
        print(f"   Redazione ok     : {'✅' if r['actually_redacted'] else '⚠️  nessun token sostituito'}")
        print(f"   Round-trip clean : {'✅' if r['round_trip_clean'] else '❌ mapping non invertibile'}")
        print(f"   After round-trip : {'✅ PASS' if af['passed'] else '❌ FAIL'}  "
              f"({af['test_count']} tests, {af['failures']} fail, {af['errors']} err)")
        print(f"   Test stabili     : {'✅' if r['tests_stable'] else '❌ comportamento cambiato'}")
        print(f"   Coverage         : {r['coverage_score']:.1f}  |  "
              f"Functionality: {r['functionality_preserved']:.1f}  |  "
              f"Leak: {'❌ YES' if r['security_leak'] else '✅ NO'}")

    # -----------------------------------------------------------------------
    # Metriche aggregate
    # -----------------------------------------------------------------------
    runnable = [r for r in results if not r.get("skipped") and not r.get("error")]

    print("\n" + "=" * 62)
    print("  METRICHE AGGREGATE")
    print("=" * 62)

    if runnable:
        coverage      = sum(r["coverage_score"]          for r in runnable) / len(runnable)
        functionality = sum(r["functionality_preserved"] for r in runnable) / len(runnable)
        leak_rate     = sum(1 for r in runnable if r["security_leak"]) / len(runnable)
        stable_rate   = sum(1 for r in runnable if r["tests_stable"])  / len(runnable)

        print(f"  Casi eseguiti          : {len(runnable)}/{len(results)}")
        print(f"  Coverage Rate          : {coverage:.2f}   (target >= 0.90)")
        print(f"  Functionality Rate     : {functionality:.2f}   (target >= 0.90)")
        print(f"  Test Stability Rate    : {stable_rate:.0%}   (target = 100%)")
        print(f"  Leak Rate              : {leak_rate:.0%}   (target = 0%)")

        # Aggiungi summary al risultato
        summary = {
            "run_at":               datetime.now().isoformat(),
            "cases_total":          len(results),
            "cases_run":            len(runnable),
            "coverage_rate":        round(coverage, 4),
            "functionality_rate":   round(functionality, 4),
            "test_stability_rate":  round(stable_rate, 4),
            "leak_rate":            round(leak_rate, 4),
        }
    else:
        summary = {}
        print("  Nessun caso eseguibile trovato.")

    # -----------------------------------------------------------------------
    # Salva JSON
    # -----------------------------------------------------------------------
    output = {"summary": summary, "cases": results}
    with open(RESULTS_OUT, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n  Risultati JSON → {RESULTS_OUT.name}")

    # -----------------------------------------------------------------------
    # Genera report Markdown
    # -----------------------------------------------------------------------
    if runnable:
        _write_report(summary, runnable)
        print(f"  Report Markdown  → {REPORT_OUT.name}")

    print()


def _write_report(summary: dict, runnable: list[dict]):
    lines = [
        "# Coding Smart Redaction Benchmark — Report v2",
        "",
        f"**Data:** {summary['run_at'][:10]}",
        f"**Strategia:** Semantic Name Mapping con verifica test pre/post redazione",
        f"**Runner:** benchmark_runner.py v2",
        "",
        "---",
        "",
        "## Metriche Aggregate",
        "",
        "| Metrica | Valore | Target |",
        "|---|---|---|",
        f"| Coverage Rate | **{summary['coverage_rate']:.2f}** | >= 0.90 |",
        f"| Functionality Rate | **{summary['functionality_rate']:.2f}** | >= 0.90 |",
        f"| Test Stability Rate | **{summary['test_stability_rate']:.0%}** | 100% |",
        f"| Leak Rate | **{summary['leak_rate']:.0%}** | 0% |",
        "",
        "---",
        "",
        "## Risultati per caso",
        "",
        "| case_id | Task | Baseline | Round-trip | After | Stable | Coverage | Func |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for r in runnable:
        bl = r["baseline"]
        af = r["after_round_trip"]
        lines.append(
            f"| {r['case_id']} | {r['task']} "
            f"| {'PASS' if bl['passed'] else 'FAIL'} ({bl['test_count']} test) "
            f"| {'✅' if r['round_trip_clean'] else '❌'} "
            f"| {'PASS' if af['passed'] else 'FAIL'} ({af['test_count']} test) "
            f"| {'✅' if r['tests_stable'] else '❌'} "
            f"| {r['coverage_score']:.1f} "
            f"| {r['functionality_preserved']:.1f} |"
        )

    lines += [
        "",
        "---",
        "",
        "## Pipeline verificata",
        "",
        "```",
        "codice originale + test",
        "        │",
        "        ▼",
        "   [1] run tests → PASS (baseline)",
        "        │",
        "        ▼",
        "   [2] apply name mapping → codice redatto (sicuro per LLM)",
        "        │",
        "        ▼",
        "   [3] LLM elabora il codice redatto (round-trip in questa versione)",
        "        │",
        "        ▼",
        "   [4] apply inverse mapping → codice restaurato",
        "        │",
        "        ▼",
        "   [5] run tests → PASS, stessi risultati del baseline ✅",
        "```",
        "",
        "## Note",
        "",
        "- **C005**: `test_real_key_is_not_placeholder` fallisce intenzionalmente dopo la redazione",
        "  (la chiave diventa `REDACTED_TOKEN_XXXX`). Questo è il comportamento corretto:",
        "  il test documenta che dopo il round-trip la chiave è tornata al valore originale.",
        "- Il runner attuale simula il passaggio LLM con un round-trip puro.",
        "  Per testare con un LLM reale, sostituire `llm_output = redacted_source`",
        "  con una chiamata API e verificare che i test rimangano stabili.",
    ]

    with open(REPORT_OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
