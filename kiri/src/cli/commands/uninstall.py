"""kiri uninstall — removes the Kiri OS service and optionally the data directory."""
from __future__ import annotations

import platform
import subprocess
from pathlib import Path
from typing import Any, Callable

from src.cli.commands.install import (
    InstallError,
    _KIRI_USER_LINUX,
    _KIRI_USER_MACOS,
    _LAUNCHD_PLIST_PATH,
    _SYSTEMD_UNIT_PATH,
    _check_privileges,
)

_RunCmd = Callable[..., Any]
_OutputFn = Callable[[str], None]


def _stop_and_disable_linux(run_cmd: _RunCmd, output_fn: _OutputFn) -> None:
    output_fn("Stopping and disabling systemd service...")
    run_cmd(["systemctl", "stop", "kiri"], check=False)
    run_cmd(["systemctl", "disable", "kiri"], check=False)
    if _SYSTEMD_UNIT_PATH.exists():
        _SYSTEMD_UNIT_PATH.unlink()
        output_fn(f"  Removed {_SYSTEMD_UNIT_PATH}")
    run_cmd(["systemctl", "daemon-reload"], check=False)


def _stop_and_disable_macos(
    run_cmd: _RunCmd,
    output_fn: _OutputFn,
    plist_path: Path = _LAUNCHD_PLIST_PATH,
) -> None:
    output_fn("Stopping launchd service...")
    run_cmd(["launchctl", "unload", "-w", str(plist_path)], check=False)
    if plist_path.exists():
        plist_path.unlink()
        output_fn(f"  Removed {plist_path}")


def _stop_and_disable_windows(run_cmd: _RunCmd, output_fn: _OutputFn) -> None:
    output_fn("Stopping Windows service...")
    run_cmd(["sc", "stop", "Kiri"], check=False)
    run_cmd(["sc", "delete", "Kiri"], check=False)


def _remove_system_user(system: str, run_cmd: _RunCmd, output_fn: _OutputFn) -> None:
    output_fn("Removing system user...")
    if system == "Linux":
        run_cmd(["userdel", _KIRI_USER_LINUX], check=False)
    elif system == "Darwin":
        run_cmd(["dscl", ".", "-delete", f"/Users/{_KIRI_USER_MACOS}"], check=False)
    elif system == "Windows":
        run_cmd(["net", "user", "kiri", "/delete"], check=False)


def run(
    data_dir: Path,
    *,
    purge: bool = False,
    output_fn: _OutputFn = print,
    run_cmd: _RunCmd = subprocess.run,
    plist_path: Path = _LAUNCHD_PLIST_PATH,
) -> None:
    """Uninstall the Kiri OS service.

    Args:
        data_dir:   Data directory to remove when purge=True.
        purge:      If True, also delete the data directory (upstream.key,
                    model, workspace, keys).  Defaults to False — the operator
                    must opt in explicitly to avoid accidental key loss.
        output_fn:  Callable used for all user-visible output.
        run_cmd:    Replacement for subprocess.run (injected in tests).
        plist_path: macOS plist path (injectable for tests).
    """
    system = platform.system()
    if system not in ("Linux", "Darwin", "Windows"):
        raise InstallError(f"Unsupported platform: {system!r}.")

    _check_privileges(system)

    output_fn(f"Uninstalling Kiri from {system}...")

    if system == "Linux":
        _stop_and_disable_linux(run_cmd, output_fn)
    elif system == "Darwin":
        _stop_and_disable_macos(run_cmd, output_fn, plist_path=plist_path)
    elif system == "Windows":
        _stop_and_disable_windows(run_cmd, output_fn)

    _remove_system_user(system, run_cmd, output_fn)

    if purge:
        if data_dir.exists():
            import shutil
            output_fn(f"Removing data directory {data_dir} ...")
            shutil.rmtree(data_dir)
            output_fn("  Done.")
        else:
            output_fn(f"  Data directory {data_dir} not found — nothing to remove.")
    else:
        output_fn("")
        output_fn(f"Data directory preserved: {data_dir}")
        output_fn("  Re-run with --purge to delete it (upstream key, model, workspace).")

    output_fn("")
    output_fn("Kiri uninstalled.")
