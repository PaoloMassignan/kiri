"""kiri summary — view and edit protection summaries (US-13, REQ-F-011)."""
from __future__ import annotations

import re
from typing import Any

import typer

from src.store.summary_store import SummaryEntry, SummaryStore

# Matches standalone decimal numbers that may be proprietary constants
# e.g. 0.0325, 2.47, 9.99 — but not plain integers like "3" or "step 1".
_CONSTANT_RE = re.compile(r"\b\d+\.\d+\b")

app = typer.Typer(help="View and edit protection summaries")


# ------------------------------------------------------------------
# Internal helpers — thin wrappers to allow patching in tests
# ------------------------------------------------------------------

def _load_summary_store() -> SummaryStore:
    from src.config.settings import Settings
    s = Settings.load()
    return SummaryStore(s.workspace / ".kiri" / "index")


def _make_summary_generator() -> Any:
    from src.config.settings import Settings
    from src.redaction.summary_generator import SummaryGenerator
    s = Settings.load()
    return SummaryGenerator(s)


# ------------------------------------------------------------------
# Commands
# ------------------------------------------------------------------

@app.command("list")
def summary_list() -> None:
    """List all protected symbols with their current summary."""
    store = _load_summary_store()
    entries = store.all_entries()

    # Hide internal manual__ prefix keys from the display — show by symbol_name
    seen: dict[str, tuple[str, SummaryEntry]] = {}
    for chunk_id, entry in entries:
        symbol = entry.symbol_name or chunk_id
        # Manual entries win over ollama for the same symbol
        if symbol not in seen or entry.source == "manual":
            seen[symbol] = (chunk_id, entry)

    if not seen:
        typer.echo("(no summaries)")
        return

    col_w = max(len(s) for s in seen) + 2
    typer.echo(f"{'Symbol':<{col_w}}{'Source':<10}Summary")
    typer.echo("-" * (col_w + 10 + 60))
    for symbol, (_, entry) in sorted(seen.items()):
        first_line = entry.text.splitlines()[0] if entry.text else ""
        # Strip comment markers for readability
        first_line = first_line.lstrip("# ").lstrip("/ ")
        if len(first_line) > 55:
            first_line = first_line[:52] + "..."
        typer.echo(f"{symbol:<{col_w}}{entry.source:<10}{first_line}")


@app.command("show")
def summary_show(
    symbol: str = typer.Argument(..., help="Symbol name to show"),
) -> None:
    """Show the full summary for a protected symbol."""
    store = _load_summary_store()
    result = store.find_by_symbol(symbol)
    if result is None:
        typer.echo(f"No summary found for: {symbol}", err=True)
        raise typer.Exit(1)

    _, entry = result
    typer.echo(entry.text)
    typer.echo("")
    typer.echo(f"Source:  {entry.source}")
    if entry.updated_at:
        typer.echo(f"Updated: {entry.updated_at}")


@app.command("set")
def summary_set(
    symbol: str = typer.Argument(..., help="Symbol name to override"),
    text: str = typer.Argument(..., help="Summary text to store"),
) -> None:
    """Set a manual summary for a protected symbol."""
    if _CONSTANT_RE.search(text):
        typer.echo(
            "⚠  Warning: the summary contains numeric literals "
            f"(e.g. {', '.join(_CONSTANT_RE.findall(text)[:3])}).\n"
            "   These may reveal proprietary constants. Remove them if sensitive."
        )

    store = _load_summary_store()
    store.set_manual(symbol, text)
    typer.echo(f"Manual summary stored for: {symbol}")


@app.command("reset")
def summary_reset(
    symbol: str | None = typer.Argument(None, help="Symbol to reset (omit for --all)"),
    all_: bool = typer.Option(False, "--all", help="Regenerate all summaries via Ollama"),
) -> None:
    """Remove manual override and regenerate from Ollama."""
    store = _load_summary_store()

    if all_:
        _reset_all(store)
        return

    if symbol is None:
        typer.echo("Error: specify a symbol or use --all", err=True)
        raise typer.Exit(1)

    _reset_one(store, symbol)


# ------------------------------------------------------------------
# Internal reset logic
# ------------------------------------------------------------------

def _reset_one(store: SummaryStore, symbol: str) -> None:
    manual_key = f"manual__{symbol}"
    has_manual = store.has(manual_key)
    auto_result = None

    # Find the auto-generated entry (non-manual) for this symbol
    for chunk_id, entry in store.all_entries():
        if not chunk_id.startswith("manual__") and (
            entry.symbol_name == symbol or symbol in entry.text
        ):
            auto_result = (chunk_id, entry)
            break

    if not has_manual and auto_result is None:
        typer.echo(f"No summary found for: {symbol}", err=True)
        raise typer.Exit(1)

    if has_manual:
        store.delete(manual_key)
        typer.echo(f"Manual override removed for: {symbol}")

    if auto_result is not None:
        chunk_id, entry = auto_result
        if entry.chunk_text:
            # Re-generate from stored chunk text
            _regenerate_one(store, chunk_id, entry.chunk_text, symbol)
            typer.echo(f"Summary regenerated via Ollama for: {symbol}")
        else:
            typer.echo(f"Reverted to Ollama summary for: {symbol}")
    elif has_manual:
        typer.echo(f"No Ollama summary available — manual override removed for: {symbol}")


def _reset_all(store: SummaryStore) -> None:
    entries = store.all_entries()
    auto_entries = [
        (chunk_id, entry)
        for chunk_id, entry in entries
        if not chunk_id.startswith("manual__") and entry.chunk_text
    ]

    if not auto_entries:
        typer.echo("No indexed chunks with stored source text to regenerate.")
        return

    generator = _make_summary_generator()
    regenerated = 0
    for chunk_id, entry in auto_entries:
        try:
            new_summary = generator.generate(chunk_id, entry.chunk_text, entry.symbol_name)
            store.save(
                chunk_id,
                new_summary,
                chunk_text=entry.chunk_text,
                symbol_name=entry.symbol_name,
            )
            regenerated += 1
        except Exception as exc:  # noqa: BLE001
            typer.echo(f"Warning: could not regenerate {chunk_id}: {exc}", err=True)

    typer.echo(f"Regenerated {regenerated}/{len(auto_entries)} summaries via Ollama.")


def _regenerate_one(
    store: SummaryStore,
    chunk_id: str,
    chunk_text: str,
    symbol_name: str,
) -> None:
    from src.redaction.summary_generator import SummaryGenerationError
    generator = _make_summary_generator()
    try:
        new_summary = generator.generate(chunk_id, chunk_text, symbol_name)
        store.save(chunk_id, new_summary, chunk_text=chunk_text, symbol_name=symbol_name)
    except SummaryGenerationError as exc:
        typer.echo(f"Error: Ollama unavailable — {exc}", err=True)
        raise typer.Exit(1) from exc
