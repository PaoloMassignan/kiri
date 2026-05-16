# PyInstaller spec — Kiri native binary
# Build: pyinstaller packaging/kiri.spec
#
# Requirements:
#   pip install pyinstaller
#   pip install -e ".[native]"   (adds llama-cpp-python)
#
# Output: dist/kiri  (Linux/macOS)  or  dist/kiri.exe  (Windows)

import sys
from pathlib import Path

block_cipher = None
root = Path(SPECPATH).parent  # kiri/

a = Analysis(
    [str(root / "src" / "main.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        # Bundle the sentence-transformers embedding model
        (str(root / ".kiri" / "models"), ".kiri/models"),
    ],
    hiddenimports=[
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
        "chromadb",
        "sentence_transformers",
        "llama_cpp",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
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
