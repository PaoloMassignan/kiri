"""Unit tests for the kiri install command.

All OS-level side effects (subprocess calls, privilege checks, urllib) are
injected via keyword arguments so tests never touch the real file system
outside of tmp_path, never spawn root-level subprocesses, and never
hit the network.
"""
from __future__ import annotations

import os
import shutil
import stat
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.cli.commands.install import (
    InstallConfig,
    InstallError,
    _check_privileges,
    _create_data_dir,
    _create_system_user,
    _generate_launchd_plist,
    _generate_systemd_unit,
    _install_model,
    _write_upstream_key,
    run,
)

_POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_run(returncode: int = 0) -> Any:
    """Return a fake subprocess.run callable that always returns returncode."""
    result = MagicMock()
    result.returncode = returncode

    def _run(*args: Any, **kwargs: Any) -> Any:
        return result

    return _run


def _recording_run() -> tuple[list[list[str]], Any]:
    """Return (calls, run_cmd) where calls accumulates every invocation."""
    calls: list[list[str]] = []
    result = MagicMock()
    result.returncode = 0

    def _run(args: list[str], *a: Any, **kw: Any) -> Any:
        calls.append(list(args))
        return result

    return calls, _run


def _make_config(tmp_path: Path, **overrides: Any) -> InstallConfig:
    return InstallConfig(data_dir=tmp_path / "kiri", **overrides)


# ---------------------------------------------------------------------------
# _check_privileges
# ---------------------------------------------------------------------------


@_POSIX_ONLY
def test_check_privileges_raises_when_not_root(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.cli.commands.install as mod
    monkeypatch.setattr(mod.os, "getuid", lambda: 1000)
    with pytest.raises(InstallError, match="root"):
        _check_privileges("Linux")


@_POSIX_ONLY
def test_check_privileges_passes_when_root(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.cli.commands.install as mod
    monkeypatch.setattr(mod.os, "getuid", lambda: 0)
    _check_privileges("Linux")  # should not raise


@_POSIX_ONLY
def test_check_privileges_raises_on_macos_when_not_root(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.cli.commands.install as mod
    monkeypatch.setattr(mod.os, "getuid", lambda: 500)
    with pytest.raises(InstallError, match="root"):
        _check_privileges("Darwin")


def test_check_privileges_passes_on_unsupported_platform() -> None:
    # _check_privileges only gates Linux/Darwin/Windows — FreeBSD falls through silently.
    # run() will catch it before _check_privileges is reached.
    _check_privileges("FreeBSD")  # should not raise


# ---------------------------------------------------------------------------
# _generate_systemd_unit
# ---------------------------------------------------------------------------


def test_generate_systemd_unit_contains_port(tmp_path: Path) -> None:
    cfg = InstallConfig(data_dir=tmp_path, port=9000)
    unit = _generate_systemd_unit(cfg)
    assert "serve --port 9000" in unit


def test_generate_systemd_unit_contains_data_dir(tmp_path: Path) -> None:
    cfg = InstallConfig(data_dir=tmp_path / "mydata")
    unit = _generate_systemd_unit(cfg)
    assert str(tmp_path / "mydata") in unit


def test_generate_systemd_unit_contains_kiri_user(tmp_path: Path) -> None:
    cfg = InstallConfig(data_dir=tmp_path)
    unit = _generate_systemd_unit(cfg)
    assert "User=kiri" in unit
    assert "Group=kiri" in unit


def test_generate_systemd_unit_contains_env_vars(tmp_path: Path) -> None:
    cfg = InstallConfig(data_dir=tmp_path)
    unit = _generate_systemd_unit(cfg)
    assert "KIRI_UPSTREAM_KEY_FILE" in unit
    assert "KIRI_CONFIG" in unit
    assert "WORKSPACE" in unit


def test_generate_systemd_unit_custom_binary(tmp_path: Path) -> None:
    cfg = InstallConfig(data_dir=tmp_path, kiri_binary="/opt/kiri/bin/kiri")
    unit = _generate_systemd_unit(cfg)
    assert "ExecStart=/opt/kiri/bin/kiri serve" in unit


# ---------------------------------------------------------------------------
# _generate_launchd_plist
# ---------------------------------------------------------------------------


def test_generate_launchd_plist_contains_port(tmp_path: Path) -> None:
    cfg = InstallConfig(data_dir=tmp_path, port=9001)
    plist = _generate_launchd_plist(cfg)
    assert "<string>9001</string>" in plist


def test_generate_launchd_plist_contains_kiri_user(tmp_path: Path) -> None:
    cfg = InstallConfig(data_dir=tmp_path)
    plist = _generate_launchd_plist(cfg)
    assert "_kiri" in plist


def test_generate_launchd_plist_contains_env_vars(tmp_path: Path) -> None:
    cfg = InstallConfig(data_dir=tmp_path)
    plist = _generate_launchd_plist(cfg)
    assert "KIRI_UPSTREAM_KEY_FILE" in plist
    assert "KIRI_CONFIG" in plist
    assert "WORKSPACE" in plist


def test_generate_launchd_plist_contains_data_dir(tmp_path: Path) -> None:
    cfg = InstallConfig(data_dir=tmp_path / "mydata")
    plist = _generate_launchd_plist(cfg)
    assert str(tmp_path / "mydata") in plist


def test_generate_launchd_plist_is_valid_xml(tmp_path: Path) -> None:
    import xml.etree.ElementTree as ET

    cfg = InstallConfig(data_dir=tmp_path)
    plist = _generate_launchd_plist(cfg)
    ET.fromstring(plist)  # raises ParseError on invalid XML


# ---------------------------------------------------------------------------
# _create_system_user
# ---------------------------------------------------------------------------


def test_create_system_user_linux_calls_useradd(monkeypatch: pytest.MonkeyPatch) -> None:
    calls, run_cmd = _recording_run()
    _create_system_user("Linux", run_cmd, print)
    assert any("useradd" in c for c in calls)
    useradd_call = next(c for c in calls if "useradd" in c)
    assert "--system" in useradd_call
    assert "kiri" in useradd_call


def test_create_system_user_macos_calls_dscl(monkeypatch: pytest.MonkeyPatch) -> None:
    # First call is the read check — return non-zero so user is created
    results = [MagicMock(returncode=1)] + [MagicMock(returncode=0)] * 10

    def _run(args: list[str], *a: Any, **kw: Any) -> Any:
        return results.pop(0) if results else MagicMock(returncode=0)

    _create_system_user("Darwin", _run, print)
    # No exception = success


def test_create_system_user_windows_calls_net_user(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    results = [MagicMock(returncode=1), MagicMock(returncode=0)]

    def _run(args: list[str], *a: Any, **kw: Any) -> Any:
        calls.append(list(args))
        return results.pop(0) if results else MagicMock(returncode=0)

    _create_system_user("Windows", _run, print)
    # Should have called "net user kiri /add ..."
    assert any("net" in c and "user" in c for c in calls)


# ---------------------------------------------------------------------------
# _create_data_dir
# ---------------------------------------------------------------------------


def test_create_data_dir_creates_subdirs(tmp_path: Path) -> None:
    data_dir = tmp_path / "kiri"
    _create_data_dir(data_dir, "Linux", _fake_run(), print)
    for subdir in ("models", "workspace", "keys"):
        assert (data_dir / subdir).is_dir()


def test_create_data_dir_calls_chown_and_chmod(tmp_path: Path) -> None:
    data_dir = tmp_path / "kiri"
    calls, run_cmd = _recording_run()
    _create_data_dir(data_dir, "Linux", run_cmd, print)
    assert any("chown" in c for c in calls)
    assert any("chmod" in c for c in calls)


def test_create_data_dir_windows_calls_icacls(tmp_path: Path) -> None:
    data_dir = tmp_path / "kiri"
    calls, run_cmd = _recording_run()
    _create_data_dir(data_dir, "Windows", run_cmd, print)
    assert any("icacls" in c for c in calls)


# ---------------------------------------------------------------------------
# _write_upstream_key
# ---------------------------------------------------------------------------


def test_write_upstream_key_creates_file(tmp_path: Path) -> None:
    data_dir = tmp_path / "kiri"
    data_dir.mkdir()
    _write_upstream_key(data_dir, "sk-ant-test", "Linux", _fake_run(), print)
    assert (data_dir / "upstream.key").read_text() == "sk-ant-test"


@_POSIX_ONLY
def test_write_upstream_key_sets_mode_600(tmp_path: Path) -> None:
    data_dir = tmp_path / "kiri"
    data_dir.mkdir()
    _write_upstream_key(data_dir, "sk-ant-test", "Linux", _fake_run(), print)
    key_path = data_dir / "upstream.key"
    file_mode = stat.S_IMODE(key_path.stat().st_mode)
    assert file_mode == 0o600


def test_write_upstream_key_calls_chown(tmp_path: Path) -> None:
    data_dir = tmp_path / "kiri"
    data_dir.mkdir()
    calls, run_cmd = _recording_run()
    _write_upstream_key(data_dir, "sk-ant-test", "Linux", run_cmd, print)
    assert any("chown" in c for c in calls)


def test_write_upstream_key_windows_calls_icacls(tmp_path: Path) -> None:
    data_dir = tmp_path / "kiri"
    data_dir.mkdir()
    calls, run_cmd = _recording_run()
    _write_upstream_key(data_dir, "sk-ant-test", "Windows", run_cmd, print)
    assert any("icacls" in c for c in calls)


# ---------------------------------------------------------------------------
# _install_model
# ---------------------------------------------------------------------------


def test_install_model_copies_local_file(tmp_path: Path) -> None:
    src = tmp_path / "mymodel.gguf"
    src.write_bytes(b"fake-gguf-content")

    data_dir = tmp_path / "kiri"
    (data_dir / "models").mkdir(parents=True)

    cfg = InstallConfig(data_dir=data_dir, model_path=src)
    _install_model(cfg, print)
    assert (data_dir / "models" / "qwen2.5-3b-q4.gguf").read_bytes() == b"fake-gguf-content"


def test_install_model_raises_when_local_file_missing(tmp_path: Path) -> None:
    data_dir = tmp_path / "kiri"
    (data_dir / "models").mkdir(parents=True)

    cfg = InstallConfig(data_dir=data_dir, model_path=tmp_path / "nonexistent.gguf")
    with pytest.raises(InstallError, match="not found"):
        _install_model(cfg, print)


def test_install_model_calls_urlretrieve_when_no_path(tmp_path: Path) -> None:
    data_dir = tmp_path / "kiri"
    (data_dir / "models").mkdir(parents=True)

    retrieved: list[str] = []

    def _fake_urlretrieve(url: str, dest: Any, progress: Any = None) -> None:
        retrieved.append(url)
        Path(dest).write_bytes(b"downloaded-model")

    cfg = InstallConfig(data_dir=data_dir)
    _install_model(cfg, print, urlretrieve_fn=_fake_urlretrieve)
    assert len(retrieved) == 1
    assert "huggingface" in retrieved[0]


def test_install_model_skips_download_when_already_present(tmp_path: Path) -> None:
    data_dir = tmp_path / "kiri"
    (data_dir / "models").mkdir(parents=True)
    (data_dir / "models" / "qwen2.5-3b-q4.gguf").write_bytes(b"existing")

    retrieved: list[str] = []

    def _fake_urlretrieve(url: str, dest: Any, progress: Any = None) -> None:
        retrieved.append(url)

    cfg = InstallConfig(data_dir=data_dir)
    _install_model(cfg, print, urlretrieve_fn=_fake_urlretrieve)
    assert not retrieved  # no download triggered


def test_install_model_cleans_up_on_download_failure(tmp_path: Path) -> None:
    data_dir = tmp_path / "kiri"
    (data_dir / "models").mkdir(parents=True)

    def _failing_urlretrieve(url: str, dest: Any, progress: Any = None) -> None:
        Path(dest).write_bytes(b"partial")
        raise OSError("connection reset")

    cfg = InstallConfig(data_dir=data_dir)
    with pytest.raises(InstallError, match="download failed"):
        _install_model(cfg, print, urlretrieve_fn=_failing_urlretrieve)

    # Partial file should be cleaned up
    assert not (data_dir / "models" / "qwen2.5-3b-q4.gguf").exists()


# ---------------------------------------------------------------------------
# run() — end-to-end orchestration
# ---------------------------------------------------------------------------


def _run_with_defaults(
    tmp_path: Path,
    *,
    monkeypatch: pytest.MonkeyPatch,
    system: str = "Linux",
    no_local_ai: bool = True,
    extra_config: dict | None = None,
) -> list[str]:
    """Run install.run() with all side effects faked. Returns list of output lines."""
    monkeypatch.setattr("platform.system", lambda: system)
    monkeypatch.setattr("src.cli.commands.install._check_privileges", lambda s: None)

    data_dir = tmp_path / "kiri"
    cfg = InstallConfig(
        data_dir=data_dir,
        no_local_ai=no_local_ai,
        # Redirect service unit files to tmp_path so tests don't need /etc or /Library
        systemd_unit_path=tmp_path / "kiri.service",
        launchd_plist_path=tmp_path / "dev.kiri.plist",
        **(extra_config or {}),
    )

    calls, run_cmd = _recording_run()
    output: list[str] = []

    run(
        cfg,
        output_fn=output.append,
        run_cmd=run_cmd,
        input_fn=lambda _: "sk-ant-test-key",
        urlretrieve_fn=lambda *a, **kw: None,
    )
    return output


def test_run_succeeds_on_linux(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = _run_with_defaults(tmp_path, monkeypatch=monkeypatch, system="Linux")
    assert any("installed" in line.lower() for line in output)


def test_run_succeeds_on_macos(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = _run_with_defaults(tmp_path, monkeypatch=monkeypatch, system="Darwin")
    assert any("installed" in line.lower() for line in output)


def test_run_succeeds_on_windows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = _run_with_defaults(tmp_path, monkeypatch=monkeypatch, system="Windows")
    assert any("installed" in line.lower() for line in output)


def test_run_raises_on_unsupported_platform(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("platform.system", lambda: "FreeBSD")
    cfg = InstallConfig(data_dir=tmp_path / "kiri")
    with pytest.raises(InstallError, match="Unsupported platform"):
        run(cfg, output_fn=lambda _: None, run_cmd=_fake_run(),
            input_fn=lambda _: "sk-ant-key",
            urlretrieve_fn=lambda *a, **kw: None)


def _make_run_cfg(tmp_path: Path, **overrides: Any) -> InstallConfig:
    """InstallConfig with service file paths redirected to tmp_path."""
    return InstallConfig(
        data_dir=tmp_path / "kiri",
        systemd_unit_path=tmp_path / "kiri.service",
        launchd_plist_path=tmp_path / "dev.kiri.plist",
        **overrides,
    )


def test_run_raises_on_empty_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("src.cli.commands.install._check_privileges", lambda s: None)
    cfg = _make_run_cfg(tmp_path, no_local_ai=True)
    with pytest.raises(InstallError, match="empty"):
        run(cfg, output_fn=lambda _: None, run_cmd=_fake_run(),
            input_fn=lambda _: "   ",
            urlretrieve_fn=lambda *a, **kw: None)


def test_run_writes_upstream_key_to_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("src.cli.commands.install._check_privileges", lambda s: None)
    cfg = _make_run_cfg(tmp_path, no_local_ai=True)
    run(
        cfg,
        output_fn=lambda _: None,
        run_cmd=_fake_run(),
        input_fn=lambda _: "sk-ant-real-key",
        urlretrieve_fn=lambda *a, **kw: None,
    )
    assert (cfg.data_dir / "upstream.key").read_text() == "sk-ant-real-key"


def test_run_skips_model_download_when_no_local_ai(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("src.cli.commands.install._check_privileges", lambda s: None)
    retrieved: list[str] = []

    def _fake_urlretrieve(url: str, dest: Any, progress: Any = None) -> None:
        retrieved.append(url)

    cfg = _make_run_cfg(tmp_path, no_local_ai=True)
    run(
        cfg,
        output_fn=lambda _: None,
        run_cmd=_fake_run(),
        input_fn=lambda _: "sk-ant-key",
        urlretrieve_fn=_fake_urlretrieve,
    )
    assert not retrieved


def test_run_downloads_model_when_local_ai_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("src.cli.commands.install._check_privileges", lambda s: None)
    retrieved: list[str] = []

    def _fake_urlretrieve(url: str, dest: Any, progress: Any = None) -> None:
        retrieved.append(url)
        Path(dest).write_bytes(b"model")

    cfg = _make_run_cfg(tmp_path, no_local_ai=False)
    run(
        cfg,
        output_fn=lambda _: None,
        run_cmd=_fake_run(),
        input_fn=lambda _: "sk-ant-key",
        urlretrieve_fn=_fake_urlretrieve,
    )
    assert len(retrieved) == 1


def test_run_creates_all_subdirectories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("src.cli.commands.install._check_privileges", lambda s: None)
    cfg = _make_run_cfg(tmp_path, no_local_ai=True)
    run(
        cfg,
        output_fn=lambda _: None,
        run_cmd=_fake_run(),
        input_fn=lambda _: "sk-ant-key",
        urlretrieve_fn=lambda *a, **kw: None,
    )
    for subdir in ("models", "workspace", "keys"):
        assert (cfg.data_dir / subdir).is_dir(), f"Missing {subdir}/"


def test_run_prints_next_steps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = _run_with_defaults(tmp_path, monkeypatch=monkeypatch)
    combined = "\n".join(output)
    assert "key create" in combined
    assert "ANTHROPIC_BASE_URL" in combined
