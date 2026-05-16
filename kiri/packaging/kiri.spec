# PyInstaller spec — Kiri native binary
# Build: cd kiri && pyinstaller packaging/kiri.spec
#
# Requirements:
#   pip install pyinstaller
#   pip install -e ".[native]"   (adds llama-cpp-python)
#
# Output: dist/kiri  (Linux/macOS)  or  dist/kiri.exe  (Windows)
#
# The GGUF model and embedding model are NOT bundled (too large).
# kiri install downloads both at installation time.

import sys
from pathlib import Path

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
    runtime_hooks=[],
    # llama_cpp is NOT bundled — its Metal/CUDA shared libs make the macOS
    # binary exceed GitHub's 2 GB asset limit.  L3 fails-open per ADR-004
    # when llama_cpp is absent; L1 and L2 remain fully active.
    excludes=["llama_cpp"],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="kiri",
    debug=False,
    strip=False,
    upx=False,
    console=True,
    onefile=True,
)
