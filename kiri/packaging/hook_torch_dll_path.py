import os
import sys

# On Windows onefile mode, PyInstaller extracts to a _MEI* temp dir.
# torch/lib DLLs depend on other DLLs that land in _MEIPASS root.
# Add both to the DLL search path before torch is imported.
if sys.platform == "win32" and hasattr(sys, "_MEIPASS") and hasattr(os, "add_dll_directory"):
    os.add_dll_directory(sys._MEIPASS)
    _torch_lib = os.path.join(sys._MEIPASS, "torch", "lib")
    if os.path.isdir(_torch_lib):
        os.add_dll_directory(_torch_lib)
