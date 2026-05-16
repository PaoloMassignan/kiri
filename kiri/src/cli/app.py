from __future__ import annotations

from datetime import UTC
from pathlib import Path

import typer

from src.cli.commands import add as cmd_add
from src.cli.commands import index as cmd_index
from src.cli.commands import inspect as cmd_inspect
from src.cli.commands import remove as cmd_remove
from src.cli.commands import status as cmd_status
from src.cli.commands.summary import app as summary_app
from src.config.settings import Settings

app = typer.Typer(name="kiri", help="Kiri management CLI")

key_app = typer.Typer(help="Manage kiri API keys")
app.add_typer(key_app, name="key")
app.add_typer(summary_app, name="summary")


def _settings() -> Settings:
    return Settings.load()


@app.command()
def add(target: str = typer.Argument(..., help="File path or @Symbol to protect")) -> None:
    try:
        msg = cmd_add.run(target, _settings())
        typer.echo(msg)
    except cmd_add.CLIError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command()
def rm(target: str = typer.Argument(..., help="File path or @Symbol to remove")) -> None:
    try:
        msg = cmd_remove.run(target, _settings())
        typer.echo(msg)
    except cmd_remove.CLIError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command()
def status() -> None:
    msg = cmd_status.run(_settings())
    typer.echo(msg)


@app.command()
def inspect(
    prompt: str | None = typer.Argument(None, help="Prompt text to inspect"),
    file: Path | None = typer.Option(
        None, "--file", "-f",
        help="Read prompt from file (avoids storing sensitive code in shell history)",
    ),
    show_redacted: bool = typer.Option(
        False, "--show-redacted", "-r",
        help="On REDACT decision, print the prompt as it would be forwarded to the LLM",
    ),
) -> None:
    if file is not None:
        if not file.exists():
            typer.echo(f"Error: file not found: {file}", err=True)
            raise typer.Exit(1)
        text = file.read_text(encoding="utf-8")
    elif prompt is not None:
        text = prompt
    else:
        typer.echo("Error: provide a prompt argument or --file <path>", err=True)
        raise typer.Exit(1)
    msg = cmd_inspect.run(text, _settings(), show_redacted=show_redacted)
    typer.echo(msg)


@key_app.command("create")
def key_create(
    expires_in: int | None = typer.Option(
        None, "--expires-in", help="Key lifetime in days (omit for no expiry)"
    ),
) -> None:
    """Generate a new kiri API key."""
    from src.keys.manager import KeyManager

    s = _settings()
    km = KeyManager(keys_dir=s.workspace / ".kiri" / "keys")
    key = km.create_key(expires_in_days=expires_in)
    typer.echo(key)


@key_app.command("list")
def key_list() -> None:
    """List all active gateway keys with expiry information."""
    from src.keys.manager import KeyManager

    s = _settings()
    km = KeyManager(keys_dir=s.workspace / ".kiri" / "keys")
    infos = [i for i in km.list_key_infos() if km.is_valid(i.key)]
    if infos:
        for info in infos:
            expiry = f"  expires {info.expires_at[:10]}" if info.expires_at else "  (no expiry)"
            typer.echo(f"{info.key}{expiry}")
    else:
        typer.echo("(no keys)")


@key_app.command("revoke")
def key_revoke(key: str = typer.Argument(..., help="Gateway key to revoke (kr-...)")) -> None:
    """Revoke a kiri API key."""
    from src.keys.manager import KeyManager

    s = _settings()
    km = KeyManager(keys_dir=s.workspace / ".kiri" / "keys")
    if km.revoke_key(key):
        typer.echo(f"Revoked {key}")
    else:
        typer.echo(f"Key not found: {key}", err=True)
        raise typer.Exit(1)


@app.command()
def index(
    path: str | None = typer.Argument(None, help="File to index into the vector store"),
    all: bool = typer.Option(False, "--all", help="Index all protected files in secrets"),
) -> None:
    """Index a file immediately (without starting the full server)."""
    if all:
        msg = cmd_index.run_all(_settings())
    elif path:
        msg = cmd_index.run(path, _settings())
    else:
        typer.echo("Error: specify a file path or use --all", err=True)
        raise typer.Exit(1)
    typer.echo(msg)


@app.command()
def log(
    tail: int = typer.Option(50, "--tail", "-n", help="Number of lines to show"),
    decision: str | None = typer.Option(
        None, "--decision", help="Filter by decision: PASS, BLOCK, REDACT"
    ),
    since: str | None = typer.Option(
        None, "--since", help="Show entries since: today, yesterday, YYYY-MM-DD"
    ),
) -> None:
    """Show the kiri audit log."""
    from datetime import datetime, timedelta

    from src.audit.log import AuditLog

    s = _settings()
    audit_log = AuditLog(log_path=s.workspace / ".kiri" / "audit.log")

    since_dt: datetime | None = None
    if since:
        today = datetime.now(tz=UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        if since == "today":
            since_dt = today
        elif since == "yesterday":
            since_dt = today - timedelta(days=1)
        else:
            since_dt = datetime.fromisoformat(since).replace(tzinfo=UTC)

    if since_dt is not None or decision is not None:
        entries = audit_log.filter(decision=decision, since=since_dt)
        if tail > 0:
            entries = entries[-tail:]
    else:
        entries = audit_log.tail(n=tail)

    if not entries:
        typer.echo("(no log entries)")
        return

    for e in entries:
        syms = f"  [{', '.join(e.matched_symbols)}]" if e.matched_symbols else ""
        sim = f"  sim={e.top_similarity:.3f}" if e.top_similarity > 0 else ""
        typer.echo(f"{e.timestamp}  {e.decision:<6}  {e.level}  {e.reason}{sim}{syms}")


@app.command()
def explain(
    n: int = typer.Option(
        1, "--entry", "-n", help="Which entry to explain (1 = most recent block/redact)"
    ),
    all_decisions: bool = typer.Option(False, "--all", help="Include PASS decisions too"),
    show_redacted: bool = typer.Option(
        False, "--show-redacted", "-r",
        help="Print the full prompt as it was forwarded to the LLM (REDACT only)",
    ),
) -> None:
    """Explain in plain language why a request was filtered."""
    from src.audit.log import AuditLog

    s = _settings()
    audit_log = AuditLog(log_path=s.workspace / ".kiri" / "audit.log")

    entries = audit_log.tail(n=0)
    if not all_decisions:
        entries = [e for e in entries if e.decision != "PASS"]

    if not entries:
        typer.echo("No filtered requests in the log.")
        return

    # Pick the N-th most recent (1 = last)
    n = max(1, n)
    if n > len(entries):
        typer.echo(f"Only {len(entries)} filtered entries in the log.")
        return

    e = entries[-n]

    lines = [
        f"Entry:     {e.timestamp}  [{e.decision}]",
        f"Level:     {e.level}",
        "",
    ]

    # Human-readable explanation per level
    if e.level == "L2":
        syms = ", ".join(e.matched_symbols) if e.matched_symbols else "(unknown)"
        lines += [
            "Why it was filtered:",
            f"  The prompt contained protected symbol(s): {syms}",
            "  L2 (whole-word symbol match) triggers a REDACT as soon as an exact",
            "  symbol name appears — regardless of similarity score.",
        ]
    elif e.level == "L1" and e.top_similarity > 0:
        lines += [
            "Why it was filtered:",
            f"  Vector similarity score: {e.top_similarity:.4f}",
        ]
        if e.matched_file:
            lines.append(f"  Closest protected source: {e.matched_file}")
        if e.top_similarity >= 0.90:
            lines += [
                "  The score is above the hard-block threshold (0.90): the prompt",
                "  is semantically very close to protected code — it was redacted.",
            ]
        else:
            lines += [
                "  The score is in the grace zone (0.75–0.90): L3 classifier was",
                "  invoked. See the reason below for the final verdict.",
            ]
    elif e.level == "L3":
        lines += [
            "Why it was filtered:",
            f"  Similarity score: {e.top_similarity:.4f} (grace zone 0.75–0.90)",
        ]
        if e.matched_file:
            lines.append(f"  Closest protected source: {e.matched_file}")
        lines += [
            "  L3 (Ollama classifier) detected explicit intent to extract",
            "  proprietary code and escalated the decision to BLOCK.",
        ]

    lines += [
        "",
        f"Reason:    {e.reason}",
    ]
    if e.matched_symbols:
        lines.append(f"Symbols:   {', '.join(e.matched_symbols)}")
    if e.matched_file:
        lines.append(f"File:      {e.matched_file}")
    if e.key_id:
        lines.append(f"Key:       {e.key_id}...")
    lines += [
        "",
        f"Excerpt:   {e.prompt_excerpt!r}",
    ]

    typer.echo("\n".join(lines))

    if show_redacted:
        if e.redacted_prompt:
            typer.echo("\n--- Prompt as forwarded to LLM ---")
            typer.echo(e.redacted_prompt)
        elif e.decision == "REDACT":
            typer.echo("\n(redacted prompt not available — recorded before this feature was added)")
        else:
            typer.echo(f"\n(no redacted prompt for {e.decision} decisions)")


@app.command()
def install(
    port: int = typer.Option(8765, "--port", "-p", help="Gateway port"),
    data_dir: Path | None = typer.Option(
        None, "--data-dir",
        help="Data directory (default: /var/lib/kiri on Linux/macOS, C:\\ProgramData\\Kiri on Windows)",
    ),
    no_local_ai: bool = typer.Option(
        False, "--no-local-ai",
        help="Skip local AI model download (L3 classifier will be disabled)",
    ),
    model_path: Path | None = typer.Option(
        None, "--model-path",
        help="Path to a pre-downloaded GGUF model file (air-gapped install)",
        exists=False,
    ),
    kiri_binary: str = typer.Option(
        "kiri", "--kiri-binary",
        help="Path or name of the kiri executable to register in the service unit",
    ),
) -> None:
    """Install Kiri as an OS service (requires root / Administrator)."""
    import platform

    from src.cli.commands.install import InstallConfig
    from src.cli.commands.install import InstallError
    from src.cli.commands.install import run as install_run

    if data_dir is None:
        data_dir = (
            Path("C:/ProgramData/Kiri")
            if platform.system() == "Windows"
            else Path("/var/lib/kiri")
        )

    config = InstallConfig(
        data_dir=data_dir,
        port=port,
        no_local_ai=no_local_ai,
        model_path=model_path,
        kiri_binary=kiri_binary,
    )

    try:
        install_run(config)
    except InstallError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command()
def serve(
    port: int | None = typer.Option(
        None, "--port", "-p",
        help="Port to listen on (overrides config; default: 8765)",
    ),
    upstream_key_file: Path | None = typer.Option(
        None, "--upstream-key-file",
        help="Path to the upstream API key file (overrides KIRI_UPSTREAM_KEY_FILE env var)",
        exists=False,
    ),
) -> None:
    """Start the gateway proxy server."""
    import os
    import uvicorn

    from src.main import create_gateway_app

    if upstream_key_file is not None:
        os.environ["KIRI_UPSTREAM_KEY_FILE"] = str(upstream_key_file)

    s = _settings()
    listen_port = port if port is not None else s.proxy_port
    application = create_gateway_app(s)
    typer.echo(f"Kiri listening on http://127.0.0.1:{listen_port}")
    uvicorn.run(application, host="127.0.0.1", port=listen_port)


if __name__ == "__main__":
    app()
