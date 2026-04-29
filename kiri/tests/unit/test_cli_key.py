from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from src.cli.app import app

runner = CliRunner()


# --- key create ---------------------------------------------------------------


def test_key_create_prints_gw_key(tmp_path: Path) -> None:
    with patch("src.cli.app._settings") as mock_settings:
        mock_settings.return_value.workspace = tmp_path
        result = runner.invoke(app, ["key", "create"])

    assert result.exit_code == 0
    assert result.output.strip().startswith("kr-")


def test_key_create_each_call_unique(tmp_path: Path) -> None:
    with patch("src.cli.app._settings") as mock_settings:
        mock_settings.return_value.workspace = tmp_path
        r1 = runner.invoke(app, ["key", "create"])
        r2 = runner.invoke(app, ["key", "create"])

    assert r1.output.strip() != r2.output.strip()


# --- key list -----------------------------------------------------------------


def test_key_list_shows_created_keys(tmp_path: Path) -> None:
    with patch("src.cli.app._settings") as mock_settings:
        mock_settings.return_value.workspace = tmp_path
        runner.invoke(app, ["key", "create"])
        result = runner.invoke(app, ["key", "list"])

    assert result.exit_code == 0
    assert "kr-" in result.output


def test_key_list_empty_shows_placeholder(tmp_path: Path) -> None:
    with patch("src.cli.app._settings") as mock_settings:
        mock_settings.return_value.workspace = tmp_path
        result = runner.invoke(app, ["key", "list"])

    assert result.exit_code == 0
    assert "no keys" in result.output


def test_key_create_with_expiry_prints_gw_key(tmp_path: Path) -> None:
    with patch("src.cli.app._settings") as mock_settings:
        mock_settings.return_value.workspace = tmp_path
        result = runner.invoke(app, ["key", "create", "--expires-in", "30"])

    assert result.exit_code == 0
    assert result.output.strip().startswith("kr-")


def test_key_list_shows_no_expiry_label(tmp_path: Path) -> None:
    with patch("src.cli.app._settings") as mock_settings:
        mock_settings.return_value.workspace = tmp_path
        runner.invoke(app, ["key", "create"])
        result = runner.invoke(app, ["key", "list"])

    assert result.exit_code == 0
    assert "no expiry" in result.output


def test_key_list_shows_expiry_date(tmp_path: Path) -> None:
    with patch("src.cli.app._settings") as mock_settings:
        mock_settings.return_value.workspace = tmp_path
        runner.invoke(app, ["key", "create", "--expires-in", "90"])
        result = runner.invoke(app, ["key", "list"])

    assert result.exit_code == 0
    assert "expires" in result.output


# --- index --------------------------------------------------------------------


def test_index_prints_result() -> None:
    with patch("src.cli.app.cmd_index.run", return_value="Indexed src/filter/pipeline.py"):
        result = runner.invoke(app, ["index", "src/filter/pipeline.py"])

    assert result.exit_code == 0
    assert "Indexed src/filter/pipeline.py" in result.output


def test_index_passes_path() -> None:
    with patch("src.cli.app.cmd_index.run", return_value="ok") as mock:
        runner.invoke(app, ["index", "src/filter/pipeline.py"])

    assert mock.call_args.args[0] == "src/filter/pipeline.py"


# --- key revoke ---------------------------------------------------------------


def test_key_revoke_removes_existing_key(tmp_path: Path) -> None:
    with patch("src.cli.app._settings") as mock_settings:
        mock_settings.return_value.workspace = tmp_path
        r_create = runner.invoke(app, ["key", "create"])
        key = r_create.output.strip()
        result = runner.invoke(app, ["key", "revoke", key])

    assert result.exit_code == 0
    assert "Revoked" in result.output


def test_key_revoke_key_no_longer_listed(tmp_path: Path) -> None:
    with patch("src.cli.app._settings") as mock_settings:
        mock_settings.return_value.workspace = tmp_path
        r_create = runner.invoke(app, ["key", "create"])
        key = r_create.output.strip()
        runner.invoke(app, ["key", "revoke", key])
        result = runner.invoke(app, ["key", "list"])

    assert key not in result.output


def test_key_revoke_unknown_key_exits_1(tmp_path: Path) -> None:
    with patch("src.cli.app._settings") as mock_settings:
        mock_settings.return_value.workspace = tmp_path
        result = runner.invoke(app, ["key", "revoke", "kr-nonexistent"])

    assert result.exit_code == 1
