# PyInstaller spec — Kiri native binary
# Build: cd kiri && pyinstaller packaging/kiri.spec
#
# Requirements:
#   pip install pyinstaller
#   pip install -e "."
#
# Output:
#   dist/kiri        (Linux onedir when --onedir passed, macOS onefile)
#   dist/kiri.exe    (Windows onefile)
#
# The GGUF model and embedding model are NOT bundled (too large).
# kiri install downloads both at installation time.

import sys
import platform
from pathlib import Path

# On Linux, PyTorch makes a onefile binary exceed 2 GB (GitHub asset limit).
# Use onedir on Linux, onefile everywhere else. Controlled here in the spec
# so the CLI invocation never passes --onedir/--onefile (not allowed with .spec).
_onedir = platform.system() == "Linux"

block_cipher = None
root = Path(SPECPATH).parent  # kiri/

a = Analysis(
    [str(root / "src" / "cli" / "app.py")],  # CLI entry point (typer)
    pathex=[str(root)],
    binaries=[],
    datas=[],
    hiddenimports=[
        # uvicorn dynamic imports
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        # chromadb — all submodules (loaded via importlib/dependency injection)
        "chromadb.api.fastapi",
        "chromadb.api.rust",
        "chromadb.api.segment",
        "chromadb.api.async_fastapi",
        "chromadb.api.async_client",
        "chromadb.app",
        "chromadb.auth",
        "chromadb.auth.basic_authn",
        "chromadb.auth.simple_rbac_authz",
        "chromadb.auth.token_authn",
        "chromadb.config",
        "chromadb.db.impl.sqlite",
        "chromadb.db.impl.sqlite_pool",
        "chromadb.db.migrations",
        "chromadb.migrations",
        "chromadb.quota.simple_quota_enforcer",
        "chromadb.rate_limit.simple_rate_limit",
        "chromadb.segment.impl.manager.local",
        "chromadb.segment.impl.manager.cache.cache",
        "chromadb.segment.impl.manager.distributed",
        "chromadb.server.fastapi",
        "chromadb.telemetry.opentelemetry.fastapi",
        "chromadb.telemetry.product.events",
        "chromadb.telemetry.product.posthog",
        # posthog — chromadb telemetry backend (must be installed at build time)
        "posthog",
        "posthog.client",
        "posthog.consumer",
        "posthog.request",
        "posthog.utils",
        "posthog.version",
        # tree-sitter language grammars loaded via importlib
        "tree_sitter_python",
        "tree_sitter_javascript",
        "tree_sitter_typescript",
        "tree_sitter_java",
        "tree_sitter_go",
        "tree_sitter_rust",
        "tree_sitter_c",
        "tree_sitter_cpp",
        "tree_sitter_c_sharp",
    ],
    hookspath=[],
    runtime_hooks=[
        str(root / "packaging" / "hook_torch_dll_path.py"),
        str(root / "packaging" / "hook_disable_chromadb_telemetry.py"),
    ],
    # llama_cpp is NOT bundled — its Metal/CUDA shared libs make the macOS
    # binary exceed GitHub's 2 GB asset limit.  L3 fails-open per ADR-004
    # when llama_cpp is absent; L1 and L2 remain fully active.
    excludes=["llama_cpp"],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

_onefile_tocs = [] if _onedir else [a.binaries, a.zipfiles, a.datas]

exe = EXE(
    pyz,
    a.scripts,
    *_onefile_tocs,
    exclude_binaries=_onedir,
    name="kiri",
    debug=False,
    strip=False,
    upx=False,
    console=True,
)

if _onedir:
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        name="kiri",
    )
