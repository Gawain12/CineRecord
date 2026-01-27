import os
import sys

# Ensure bundled DLLs are discoverable early on Windows
if os.name == "nt":
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass and os.path.isdir(meipass):
        try:
            os.add_dll_directory(meipass)
        except Exception:
            pass
        os.environ["PATH"] = meipass + os.pathsep + os.environ.get("PATH", "")
