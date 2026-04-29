from __future__ import annotations

from unittest.mock import patch

from typer.testing import CliRunner

from src.cli.app import app
from src.cli.commands.add import CLIError as AddCLIError
from src.cli.commands.remove import CLIError as RemoveCLIError

runner = CliRunner()


# --- inspect ------------------------------------------------------------------


def test_app_inspect_prints_result() -> None:
    with patch("src.cli.app.cmd_inspect.run", return_value="Decision : PASS") as mock:
        result = runner.invoke(app, ["inspect", "explain quicksort"])

    mock.assert_called_once()
    assert "Decision : PASS" in result.output
    assert result.exit_code == 0


def test_app_inspect_passes_prompt() -> None:
    with patch("src.cli.app.cmd_inspect.run", return_value="ok") as mock:
        runner.invoke(app, ["inspect", "my prompt here"])

    prompt_arg = mock.call_args.args[0]
    assert prompt_arg == "my prompt here"


def test_app_inspect_file_option_reads_from_file(tmp_path) -> None:
    """--file reads the prompt from disk, keeping it out of shell history."""
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("describe the risk algorithm", encoding="utf-8")

    with patch("src.cli.app.cmd_inspect.run", return_value="Decision : PASS") as mock:
        result = runner.invoke(app, ["inspect", "--file", str(prompt_file)])

    assert result.exit_code == 0
    assert mock.call_args.args[0] == "describe the risk algorithm"


def test_app_inspect_file_missing_exits_1(tmp_path) -> None:
    with patch("src.cli.app.cmd_inspect.run", return_value="ok"):
        result = runner.invoke(app, ["inspect", "--file", str(tmp_path / "nonexistent.txt")])

    assert result.exit_code == 1


def test_app_inspect_no_arg_no_file_exits_1() -> None:
    result = runner.invoke(app, ["inspect"])

    assert result.exit_code == 1


# --- serve --------------------------------------------------------------------


def test_serve_binds_to_localhost() -> None:
    """gateway serve must bind to 127.0.0.1, never 0.0.0.0."""
    import uvicorn

    from src.config.settings import Settings

    calls: list[dict] = []

    def fake_run(app, **kwargs):
        calls.append(kwargs)

    # create_gateway_app is imported locally inside serve(), patch at the source
    with patch.object(uvicorn, "run", fake_run), \
         patch("src.main.create_gateway_app", return_value=None), \
         patch("src.cli.app._settings", return_value=Settings()):
        runner.invoke(app, ["serve"])

    assert calls, "uvicorn.run was never called"
    assert calls[0].get("host") == "127.0.0.1", (
        f"gateway serve must bind to 127.0.0.1, got: {calls[0].get('host')}"
    )


# --- add ----------------------------------------------------------------------


def test_app_add_prints_result() -> None:
    with patch("src.cli.app.cmd_add.run", return_value="Added @Foo to protected symbols"):
        result = runner.invoke(app, ["add", "@Foo"])

    assert "Added @Foo" in result.output
    assert result.exit_code == 0


def test_app_add_passes_target() -> None:
    with patch("src.cli.app.cmd_add.run", return_value="ok") as mock:
        runner.invoke(app, ["add", "@Bar"])

    target_arg = mock.call_args.args[0]
    assert target_arg == "@Bar"


def test_app_add_exits_1_on_cli_error() -> None:
    err = AddCLIError("Path does not exist: missing.py")
    with patch("src.cli.app.cmd_add.run", side_effect=err):
        result = runner.invoke(app, ["add", "missing.py"])

    assert result.exit_code == 1
    assert "Error" in result.output


# --- rm -----------------------------------------------------------------------


def test_app_rm_prints_result() -> None:
    with patch("src.cli.app.cmd_remove.run", return_value="Removed @Foo from protected symbols"):
        result = runner.invoke(app, ["rm", "@Foo"])

    assert "Removed @Foo" in result.output
    assert result.exit_code == 0


def test_app_rm_passes_target() -> None:
    with patch("src.cli.app.cmd_remove.run", return_value="ok") as mock:
        runner.invoke(app, ["rm", "@Bar"])

    target_arg = mock.call_args.args[0]
    assert target_arg == "@Bar"


def test_app_rm_exits_1_on_cli_error() -> None:
    with patch("src.cli.app.cmd_remove.run", side_effect=RemoveCLIError("not found")):
        result = runner.invoke(app, ["rm", "missing.py"])

    assert result.exit_code == 1


# --- status -------------------------------------------------------------------


def test_app_status_prints_result() -> None:
    with patch("src.cli.app.cmd_status.run", return_value="=== Gateway Protection Status ==="):
        result = runner.invoke(app, ["status"])

    assert "Gateway Protection Status" in result.output
    assert result.exit_code == 0
