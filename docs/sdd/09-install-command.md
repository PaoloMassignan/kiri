# SDD-09 — `kiri install` Command

## 1. Purpose

`kiri install` installs Kiri as an OS-managed service on Linux, macOS, and
Windows.  It performs the following steps in order:

1. Privilege check (root / Administrator required)
2. Create the `kiri` system account
3. Create the data directory (`/var/lib/kiri` by default) with restricted permissions
4. Prompt for the upstream Anthropic key and write it as a mode-600 file
5. Install and enable the OS service unit
6. Download or copy the GGUF model (unless `--no-local-ai`)

After `install`, operators run `kiri key create` to generate developer keys and
set `ANTHROPIC_BASE_URL=http://127.0.0.1:<port>` in their shell environment.

---

## 2. CLI Interface

```
kiri install [OPTIONS]

Options:
  --port, -p INTEGER           Gateway port  [default: 8765]
  --data-dir PATH              Data directory
                               [default: /var/lib/kiri  |  C:\ProgramData\Kiri]
  --no-local-ai                Skip local AI model download (L3 disabled)
  --model-path PATH            Pre-downloaded GGUF model file (air-gapped)
  --kiri-binary TEXT           Path or name of the kiri executable
                               [default: kiri]
```

---

## 3. Data Directory Layout

```
/var/lib/kiri/               (Linux / macOS default; C:\ProgramData\Kiri on Windows)
├── upstream.key             mode 600, owned by kiri — upstream Anthropic key
├── config.yaml              optional; settings override
├── models/
│   └── qwen2.5-3b-q4.gguf  GGUF model (downloaded by install or copied from --model-path)
├── workspace/               kiri workspace — .kiri/secrets, vectors, audit log
└── keys/                    developer kr- keys
```

Permissions:
- Directory: `750`, owner `kiri`:`kiri`
- `upstream.key`: `600`, owner `kiri`:`kiri`

---

## 4. OS Service Units

### 4.1 Linux — systemd

Written to `/etc/systemd/system/kiri.service`.

Key properties:
- `User=kiri`, `Group=kiri`
- `KIRI_UPSTREAM_KEY_FILE=/var/lib/kiri/upstream.key`
- `KIRI_CONFIG=/var/lib/kiri/config.yaml`
- `WORKSPACE=/var/lib/kiri/workspace`
- Hardening: `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=strict`, `ReadWritePaths`

Activation:
```
systemctl daemon-reload
systemctl enable kiri
systemctl start kiri
```

### 4.2 macOS — launchd

Written to `/Library/LaunchDaemons/dev.kiri.plist`.

Key properties:
- `UserName=_kiri`
- Same environment variables as Linux
- `RunAtLoad=true`, `KeepAlive=true`
- stdout/stderr → `/var/log/kiri/kiri.log`

Activation:
```
launchctl load -w /Library/LaunchDaemons/dev.kiri.plist
```

### 4.3 Windows — Service Control Manager

Registers a Windows Service named `Kiri` via `sc create`.

- Runs as `NT AUTHORITY\LocalService`
- Binary path: `"<kiri_binary>" serve --port <port> --upstream-key-file "<data_dir>\upstream.key"`
- Key ACL: `Administrators:F`, `SYSTEM:F`, `kiri:R` (read-only for the service account)

Start: `sc start Kiri`

---

## 5. Model Installation

| Flag | Behaviour |
|---|---|
| *(none)* | Download from HuggingFace if not already present |
| `--model-path <file>` | Copy local file (air-gapped / enterprise networks) |
| `--no-local-ai` | Skip entirely — L3 classifier unavailable |

Default model: `qwen2.5-3b-instruct-q4_k_m.gguf` (~2.3 GB).

Download URL: `https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf`

Partial downloads are cleaned up on failure so a retry does not leave
a corrupt model file.

---

## 6. Key Implementation Details

### Testability

`install.run()` accepts injectable dependencies via keyword arguments:

| Parameter | Default | Purpose |
|---|---|---|
| `output_fn` | `print` | All user-visible output |
| `run_cmd` | `subprocess.run` | All subprocess calls |
| `input_fn` | `getpass.getpass` | Upstream key prompt |
| `urlretrieve_fn` | `urllib.request.urlretrieve` | Model download |

`InstallConfig.systemd_unit_path` and `launchd_plist_path` default to the
real system paths but can be redirected to `tmp_path` in unit tests.

### Privilege Check

`_check_privileges(system)` is a separate module-level function, making it
patchable in tests via `monkeypatch.setattr`.  On POSIX it checks
`os.getuid() == 0`; on Windows it calls `ctypes.windll.shell32.IsUserAnAdmin()`.

### `_generate_systemd_unit` / `_generate_launchd_plist`

Pure functions: they take an `InstallConfig` and return a `str`.  No
subprocess calls.  Tested directly in unit tests without any mocking.

---

## 7. Post-Install Checklist

```bash
# Linux
sudo systemctl start kiri
sudo systemctl status kiri

# Create developer key (run as a developer, not as root)
kiri key create

# Point Claude Code at the gateway
export ANTHROPIC_BASE_URL=http://127.0.0.1:8765

# Verify
kiri status
```

---

## 8. Uninstall

Not implemented in `kiri install` — use platform tools:

```bash
# Linux
sudo systemctl disable --now kiri
sudo rm /etc/systemd/system/kiri.service
sudo userdel kiri
sudo rm -rf /var/lib/kiri

# macOS
sudo launchctl unload /Library/LaunchDaemons/dev.kiri.plist
sudo rm /Library/LaunchDaemons/dev.kiri.plist

# Windows (run as Administrator)
sc stop Kiri
sc delete Kiri
net user kiri /delete
Remove-Item -Recurse "C:\ProgramData\Kiri"
```
