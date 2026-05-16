"""Unit tests for kiri uninstall."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.cli.commands.uninstall import run

_POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_run(returncode: int = 0) -> Any:
    result = MagicMock()
    result.returncode = returncode
    result.stdout = ""

    def _run(*args: Any, **kwargs: Any) -> Any:
        return result

    return _run


def _recording_run() -> tuple[list[list[str]], Any]:
    calls: list[list[str]] = []
    result = MagicMock()
    result.returncode = 0
    result.stdout = ""

    def _run(args: list[str], *a: Any, **kw: Any) -> Any:
        calls.append(list(args))
        return result

    return calls, _run


def _run_uninstall(
    tmp_path: Path,
    *,
    monkeypatch: pytest.MonkeyPatch,
    system: str = "Linux",
    purge: bool = False,
) -> list[str]:
    monkeypatch.setattr("platform.system", lambda: system)
    monkeypatch.setattr("src.cli.commands.uninstall._check_privileges", lambda s: None)

    output: list[str] = []
    calls, run_cmd = _recording_run()
    plist = tmp_path / "dev.kiri.plist"

    run(
        tmp_path / "kiri",
        purge=purge,
        output_fn=output.append,
        run_cmd=run_cmd,
        plist_path=plist,
    )
    return output


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_uninstall_linux_calls_systemctl_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("src.cli.commands.uninstall._check_privileges", lambda s: None)
    calls, run_cmd = _recording_run()
    run(tmp_path / "kiri", output_fn=lambda _: None, run_cmd=run_cmd,
        plist_path=tmp_path / "plist")
    assert any(c[:3] == ["systemctl", "stop", "kiri"] for c in calls)


def test_uninstall_linux_calls_systemctl_disable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("src.cli.commands.uninstall._check_privileges", lambda s: None)
    calls, run_cmd = _recording_run()
    run(tmp_path / "kiri", output_fn=lambda _: None, run_cmd=run_cmd,
        plist_path=tmp_path / "plist")
    assert any(c[:3] == ["systemctl", "disable", "kiri"] for c in calls)


def test_uninstall_linux_removes_systemd_unit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("src.cli.commands.uninstall._check_privileges", lambda s: None)
    # Create a fake unit file at the patched SYSTEMD_UNIT_PATH
    import src.cli.commands.uninstall as mod
    fake_unit = tmp_path / "kiri.service"
    fake_unit.write_text("[Unit]\n")
    monkeypatch.setattr(mod, "_SYSTEMD_UNIT_PATH", fake_unit)
    run(tmp_path / "kiri", output_fn=lambda _: None, run_cmd=_fake_run(),
        plist_path=tmp_path / "plist")
    assert not fake_unit.exists()


def test_uninstall_macos_calls_launchctl_unload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr("src.cli.commands.uninstall._check_privileges", lambda s: None)
    calls, run_cmd = _recording_run()
    plist = tmp_path / "dev.kiri.plist"
    run(tmp_path / "kiri", output_fn=lambda _: None, run_cmd=run_cmd, plist_path=plist)
    assert any("launchctl" in c and "unload" in c for c in calls)


def test_uninstall_macos_removes_plist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr("src.cli.commands.uninstall._check_privileges", lambda s: None)
    plist = tmp_path / "dev.kiri.plist"
    plist.write_text("<plist/>")
    run(tmp_path / "kiri", output_fn=lambda _: None, run_cmd=_fake_run(), plist_path=plist)
    assert not plist.exists()


def test_uninstall_windows_calls_sc_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("platform.system", lambda: "Windows")
    monkeypatch.setattr("src.cli.commands.uninstall._check_privileges", lambda s: None)
    calls, run_cmd = _recording_run()
    run(tmp_path / "kiri", output_fn=lambda _: None, run_cmd=run_cmd,
        plist_path=tmp_path / "plist")
    assert any(c[:3] == ["sc", "stop", "Kiri"] for c in calls)


def test_uninstall_windows_calls_sc_delete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("platform.system", lambda: "Windows")
    monkeypatch.setattr("src.cli.commands.uninstall._check_privileges", lambda s: None)
    calls, run_cmd = _recording_run()
    run(tmp_path / "kiri", output_fn=lambda _: None, run_cmd=run_cmd,
        plist_path=tmp_path / "plist")
    assert any(c[:3] == ["sc", "delete", "Kiri"] for c in calls)


def test_uninstall_purge_removes_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("src.cli.commands.uninstall._check_privileges", lambda s: None)
    data_dir = tmp_path / "kiri"
    data_dir.mkdir()
    (data_dir / "upstream.key").write_text("sk-ant-key")

    run(data_dir, purge=True, output_fn=lambda _: None, run_cmd=_fake_run(),
        plist_path=tmp_path / "plist")
    assert not data_dir.exists()


def test_uninstall_no_purge_preserves_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("src.cli.commands.uninstall._check_privileges", lambda s: None)
    data_dir = tmp_path / "kiri"
    data_dir.mkdir()
    (data_dir / "upstream.key").write_text("sk-ant-key")

    run(data_dir, purge=False, output_fn=lambda _: None, run_cmd=_fake_run(),
        plist_path=tmp_path / "plist")
    assert data_dir.exists()


def test_uninstall_purge_handles_missing_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("src.cli.commands.uninstall._check_privileges", lambda s: None)
    # data_dir does not exist — should not raise
    run(tmp_path / "nonexistent", purge=True, output_fn=lambda _: None,
        run_cmd=_fake_run(), plist_path=tmp_path / "plist")


def test_uninstall_prints_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = _run_uninstall(tmp_path, monkeypatch=monkeypatch)
    assert any("uninstalled" in line.lower() for line in output)


def test_uninstall_raises_on_unsupported_platform(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.cli.commands.install import InstallError
    monkeypatch.setattr("platform.system", lambda: "FreeBSD")
    with pytest.raises(InstallError, match="Unsupported"):
        run(tmp_path / "kiri", output_fn=lambda _: None, run_cmd=_fake_run(),
            plist_path=tmp_path / "plist")
