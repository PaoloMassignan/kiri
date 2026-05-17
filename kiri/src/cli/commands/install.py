"""kiri install — installs Kiri as an OS service.

Supports Linux (systemd), macOS (launchd), and Windows (Service Control Manager).
Must be run with administrator / root privileges.
"""
from __future__ import annotations

import dataclasses
import getpass
import os
import platform
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Any, Callable

_MODEL_URL = (
    "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/"
    "qwen2.5-3b-instruct-q4_k_m.gguf"
)
_MODEL_FILENAME = "qwen2.5-3b-q4.gguf"

_KIRI_USER_LINUX = "kiri"
_KIRI_USER_MACOS = "_kiri"

_SYSTEMD_UNIT_PATH = Path("/etc/systemd/system/kiri.service")
_LAUNCHD_PLIST_PATH = Path("/Library/LaunchDaemons/dev.kiri.plist")

_RunCmd = Callable[..., Any]
_OutputFn = Callable[[str], None]


class InstallError(Exception):
    pass


@dataclasses.dataclass
class InstallConfig:
    data_dir: Path
    port: int = 8765
    no_local_ai: bool = False
    model_path: Path | None = None  # pre-downloaded GGUF for air-gapped installs
    kiri_binary: str = "kiri"       # path or name of the kiri executable
    # Override service file destinations; used in tests to redirect to tmp_path
    systemd_unit_path: Path = dataclasses.field(default_factory=lambda: _SYSTEMD_UNIT_PATH)
    launchd_plist_path: Path = dataclasses.field(default_factory=lambda: _LAUNCHD_PLIST_PATH)


# ---------------------------------------------------------------------------
# Privilege check
# ---------------------------------------------------------------------------


def _check_privileges(system: str) -> None:
    if system == "Windows":
        try:
            import ctypes
            if not ctypes.windll.shell32.IsUserAnAdmin():  # type: ignore[attr-defined]
                raise InstallError("kiri install must be run as Administrator on Windows.")
        except AttributeError:
            pass  # non-Windows ctypes — skip
    elif system in ("Linux", "Darwin"):
        if os.getuid() != 0:
            raise InstallError("kiri install must be run as root (use sudo).")


# ---------------------------------------------------------------------------
# System user creation
# ---------------------------------------------------------------------------

_MACOS_UID_MIN = 300
_MACOS_UID_MAX = 400


def _find_free_uid_macos(run_cmd: _RunCmd) -> int:
    """Return the first unused UID in [_MACOS_UID_MIN, _MACOS_UID_MAX).

    macOS reserves UIDs < 500 for system accounts (_kiri, _www, etc.).
    We scan the range so we don't collide with any existing account.
    """
    for uid in range(_MACOS_UID_MIN, _MACOS_UID_MAX):
        result = run_cmd(
            ["dscl", ".", "-search", "/Users", "UniqueID", str(uid)],
            check=False,
        )
        # dscl exits 0 and prints nothing if the UID is free
        if result.returncode == 0 and not (result.stdout or "").strip():
            return uid
    raise InstallError(
        f"No free UID found in range [{_MACOS_UID_MIN}, {_MACOS_UID_MAX}). "
        "Remove a system account or expand the search range."
    )


def _create_system_user(system: str, run_cmd: _RunCmd, output_fn: _OutputFn) -> None:
    output_fn("Creating system user...")
    if system == "Linux":
        # Ignore error if user already exists (exit code 9)
        result = run_cmd(
            ["useradd", "--system", "--no-create-home",
             "--shell", "/usr/sbin/nologin", _KIRI_USER_LINUX],
            check=False,
        )
        if result.returncode not in (0, 9):
            raise InstallError(f"useradd failed (exit {result.returncode})")
    elif system == "Darwin":
        result = run_cmd(
            ["dscl", ".", "-read", f"/Users/{_KIRI_USER_MACOS}"],
            check=False,
        )
        if result.returncode != 0:
            uid = _find_free_uid_macos(run_cmd)
            run_cmd(["dscl", ".", "-create", f"/Users/{_KIRI_USER_MACOS}"], check=True)
            run_cmd(["dscl", ".", "-create", f"/Users/{_KIRI_USER_MACOS}",
                     "UserShell", "/usr/bin/false"], check=True)
            run_cmd(["dscl", ".", "-create", f"/Users/{_KIRI_USER_MACOS}",
                     "RealName", "Kiri Service Account"], check=True)
            run_cmd(["dscl", ".", "-create", f"/Users/{_KIRI_USER_MACOS}",
                     "UniqueID", str(uid)], check=True)
            run_cmd(["dscl", ".", "-create", f"/Users/{_KIRI_USER_MACOS}",
                     "PrimaryGroupID", "80"], check=True)
    elif system == "Windows":
        result = run_cmd(
            ["net", "user", "kiri"],
            check=False,
        )
        if result.returncode != 0:
            run_cmd(
                ["net", "user", "kiri", "/add", "/passwordreq:no",
                 "/comment:Kiri Service Account"],
                check=True,
            )


def _kiri_user(system: str) -> str:
    return _KIRI_USER_MACOS if system == "Darwin" else _KIRI_USER_LINUX


# ---------------------------------------------------------------------------
# Data directory setup
# ---------------------------------------------------------------------------


def _create_data_dir(
    data_dir: Path, system: str, run_cmd: _RunCmd, output_fn: _OutputFn
) -> None:
    output_fn(f"Creating data directory {data_dir} ...")
    for subdir in ("", "models", "workspace", "keys"):
        (data_dir / subdir).mkdir(parents=True, exist_ok=True)

    if system in ("Linux", "Darwin"):
        user = _kiri_user(system)
        run_cmd(["chown", "-R", f"{user}:{user}", str(data_dir)], check=True)
        run_cmd(["chmod", "750", str(data_dir)], check=True)
    elif system == "Windows":
        # Grant the kiri service account full control; revoke Everyone
        run_cmd(
            ["icacls", str(data_dir), "/inheritance:r",
             "/grant:r", "kiri:(OI)(CI)F", "/grant:r", "Administrators:(OI)(CI)F"],
            check=True,
        )


# ---------------------------------------------------------------------------
# Upstream key
# ---------------------------------------------------------------------------


def _write_upstream_key(
    data_dir: Path, key: str, system: str, run_cmd: _RunCmd, output_fn: _OutputFn
) -> None:
    output_fn("Writing upstream key...")
    key_path = data_dir / "upstream.key"
    key_path.write_text(key, encoding="utf-8")

    if system in ("Linux", "Darwin"):
        user = _kiri_user(system)
        key_path.chmod(0o600)
        run_cmd(["chown", f"{user}:{user}", str(key_path)], check=True)
    elif system == "Windows":
        run_cmd(
            ["icacls", str(key_path), "/inheritance:r",
             "/grant:r", "kiri:R", "/grant:r", "Administrators:F",
             "/grant:r", "SYSTEM:F"],
            check=True,
        )


# ---------------------------------------------------------------------------
# Default config.yaml
# ---------------------------------------------------------------------------


def _generate_config_yaml(config: InstallConfig) -> str:
    """Return a minimal config.yaml suited for the native binary distribution.

    When local AI is enabled the file points llm_backend at the GGUF model
    that was downloaded (or copied) by _install_model.  When --no-local-ai is
    used we omit the llm_backend key so the gateway defaults to "ollama" and
    L3 fails-open gracefully (ADR-004) if Ollama is not running.
    """
    model_path = config.data_dir / "models" / _MODEL_FILENAME
    lines: list[str] = [
        f"workspace: {config.data_dir / 'workspace'}",
        f"proxy_port: {config.port}",
    ]
    if not config.no_local_ai:
        lines += [
            "llm_backend: llama_cpp",
            f"llm_model_path: {model_path}",
        ]
    return "\n".join(lines) + "\n"


def _write_config_yaml(
    config: InstallConfig, system: str, run_cmd: _RunCmd, output_fn: _OutputFn
) -> None:
    cfg_path = config.data_dir / "config.yaml"
    if cfg_path.exists():
        output_fn(f"  config.yaml already exists — skipping (remove to regenerate).")
        return
    output_fn("Writing default config.yaml...")
    cfg_path.write_text(_generate_config_yaml(config), encoding="utf-8")
    if system in ("Linux", "Darwin"):
        user = _kiri_user(system)
        run_cmd(["chown", f"{user}:{user}", str(cfg_path)], check=True)


# ---------------------------------------------------------------------------
# Service unit generation (pure functions — easy to test)
# ---------------------------------------------------------------------------


def _generate_systemd_unit(config: InstallConfig) -> str:
    return (
        "[Unit]\n"
        "Description=Kiri AI Gateway\n"
        "Documentation=https://github.com/PaoloMassignan/kiri\n"
        "After=network.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f"User={_KIRI_USER_LINUX}\n"
        f"Group={_KIRI_USER_LINUX}\n"
        f"ExecStart={config.kiri_binary} serve --port {config.port}\n"
        f"Environment=KIRI_UPSTREAM_KEY_FILE={config.data_dir}/upstream.key\n"
        f"Environment=KIRI_CONFIG={config.data_dir}/config.yaml\n"
        f"Environment=WORKSPACE={config.data_dir}/workspace\n"
        "Restart=always\n"
        "RestartSec=5\n"
        "NoNewPrivileges=true\n"
        "PrivateTmp=true\n"
        "ProtectSystem=strict\n"
        f"ReadWritePaths={config.data_dir}\n"
        "\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )


def _generate_launchd_plist(config: InstallConfig) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"\n'
        '  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        '  <key>Label</key>             <string>dev.kiri</string>\n'
        '  <key>ProgramArguments</key>\n'
        "  <array>\n"
        f"    <string>{config.kiri_binary}</string>\n"
        "    <string>serve</string>\n"
        "    <string>--port</string>\n"
        f"    <string>{config.port}</string>\n"
        "  </array>\n"
        f'  <key>UserName</key>          <string>{_KIRI_USER_MACOS}</string>\n'
        "  <key>RunAtLoad</key>         <true/>\n"
        "  <key>KeepAlive</key>         <true/>\n"
        "  <key>EnvironmentVariables</key>\n"
        "  <dict>\n"
        f"    <key>KIRI_UPSTREAM_KEY_FILE</key> <string>{config.data_dir}/upstream.key</string>\n"
        f"    <key>KIRI_CONFIG</key>            <string>{config.data_dir}/config.yaml</string>\n"
        f"    <key>WORKSPACE</key>              <string>{config.data_dir}/workspace</string>\n"
        "  </dict>\n"
        '  <key>StandardOutPath</key>   <string>/var/log/kiri/kiri.log</string>\n'
        '  <key>StandardErrorPath</key> <string>/var/log/kiri/kiri.log</string>\n'
        "</dict>\n"
        "</plist>\n"
    )


# ---------------------------------------------------------------------------
# Service installation
# ---------------------------------------------------------------------------


def _install_service_linux(
    config: InstallConfig, run_cmd: _RunCmd, output_fn: _OutputFn
) -> None:
    output_fn("Installing systemd service...")
    unit = _generate_systemd_unit(config)
    config.systemd_unit_path.write_text(unit, encoding="utf-8")
    run_cmd(["systemctl", "daemon-reload"], check=True)
    run_cmd(["systemctl", "enable", "kiri"], check=True)
    output_fn(f"  systemd unit installed at {config.systemd_unit_path}")
    output_fn("  Start with: sudo systemctl start kiri")


def _install_service_macos(
    config: InstallConfig, run_cmd: _RunCmd, output_fn: _OutputFn
) -> None:
    output_fn("Installing launchd service...")
    plist = _generate_launchd_plist(config)
    config.launchd_plist_path.write_text(plist, encoding="utf-8")
    run_cmd(
        ["launchctl", "load", "-w", str(config.launchd_plist_path)],
        check=True,
    )
    output_fn(f"  launchd plist installed at {config.launchd_plist_path}")
    output_fn("  Service starts automatically at boot.")


def _install_service_windows(
    config: InstallConfig, run_cmd: _RunCmd, output_fn: _OutputFn
) -> None:
    output_fn("Installing Windows service...")
    bin_path = (
        f'"{config.kiri_binary}" serve --port {config.port} '
        f'--upstream-key-file "{config.data_dir}\\upstream.key"'
    )
    result = run_cmd(["sc", "query", "Kiri"], check=False)
    if result.returncode == 0:
        output_fn("  Service already exists — updating binary path.")
        run_cmd(["sc", "config", "Kiri", f"binPath= {bin_path}"], check=True)
    else:
        run_cmd(
            ["sc", "create", "Kiri",
             f"binPath= {bin_path}",
             "DisplayName= Kiri AI Gateway",
             "start= auto",
             "obj= NT AUTHORITY\\LocalService"],
            check=True,
        )
    output_fn("  Start with: sc start Kiri")


def _install_service(
    config: InstallConfig, system: str, run_cmd: _RunCmd, output_fn: _OutputFn
) -> None:
    if system == "Linux":
        _install_service_linux(config, run_cmd, output_fn)
    elif system == "Darwin":
        _install_service_macos(config, run_cmd, output_fn)
    elif system == "Windows":
        _install_service_windows(config, run_cmd, output_fn)


# ---------------------------------------------------------------------------
# Model installation
# ---------------------------------------------------------------------------


def _install_model(
    config: InstallConfig,
    output_fn: _OutputFn,
    urlretrieve_fn: Callable[..., Any] = urllib.request.urlretrieve,
) -> None:
    dest = config.data_dir / "models" / _MODEL_FILENAME

    if config.model_path is not None:
        if not config.model_path.exists():
            raise InstallError(f"Model file not found: {config.model_path}")
        output_fn(f"Copying model from {config.model_path} ...")
        shutil.copy2(config.model_path, dest)
        output_fn(f"  Model copied to {dest}")
        return

    if dest.exists():
        output_fn(f"Model already present at {dest} — skipping download.")
        return

    output_fn(f"Downloading model to {dest} ...")
    output_fn(f"  Source: {_MODEL_URL}")

    _downloaded: list[int] = [0]

    def _progress(block_num: int, block_size: int, total_size: int) -> None:
        downloaded = min(block_num * block_size, total_size)
        if total_size > 0 and downloaded - _downloaded[0] > 50 * 1024 * 1024:
            _downloaded[0] = downloaded
            pct = downloaded * 100 // total_size
            output_fn(f"  {pct}% ({downloaded // (1024 * 1024)} MB / {total_size // (1024 * 1024)} MB)")

    try:
        urlretrieve_fn(_MODEL_URL, dest, _progress)
    except Exception as exc:
        dest.unlink(missing_ok=True)
        raise InstallError(f"Model download failed: {exc}") from exc

    output_fn(f"  Model downloaded to {dest}")


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


def run(
    config: InstallConfig,
    *,
    output_fn: _OutputFn = print,
    run_cmd: _RunCmd = subprocess.run,
    input_fn: Callable[[str], str] = getpass.getpass,
    urlretrieve_fn: Callable[..., Any] = urllib.request.urlretrieve,
) -> None:
    """Install Kiri as an OS service (requires root / Administrator)."""
    system = platform.system()
    if system not in ("Linux", "Darwin", "Windows"):
        raise InstallError(f"Unsupported platform: {system!r}. Supported: Linux, macOS, Windows.")

    _check_privileges(system)

    output_fn(f"Installing Kiri on {system}...")

    _create_system_user(system, run_cmd, output_fn)
    _create_data_dir(config.data_dir, system, run_cmd, output_fn)

    key = input_fn("Upstream Anthropic key (sk-ant-...): ")
    if not key.strip():
        raise InstallError("Upstream key cannot be empty.")
    _write_upstream_key(config.data_dir, key.strip(), system, run_cmd, output_fn)
    _write_config_yaml(config, system, run_cmd, output_fn)

    _install_service(config, system, run_cmd, output_fn)

    if not config.no_local_ai:
        _install_model(config, output_fn, urlretrieve_fn)

    output_fn("")
    output_fn("Kiri installed successfully.")
    output_fn("")
    output_fn("Next steps:")
    if system == "Linux":
        output_fn("  sudo systemctl start kiri")
    elif system == "Darwin":
        output_fn("  sudo launchctl start dev.kiri")
    elif system == "Windows":
        output_fn("  sc start Kiri")
    output_fn(f"  kiri key create   # generate a developer key")
    output_fn(f"  export ANTHROPIC_BASE_URL=http://127.0.0.1:{config.port}")
