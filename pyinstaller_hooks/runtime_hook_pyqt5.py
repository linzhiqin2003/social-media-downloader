"""Runtime hook to fix PyQt5 DLL loading on Windows."""
import os
import sys

if sys.platform == "win32" and getattr(sys, "frozen", False):
    base = sys._MEIPASS
    # Add Qt5 bin directory to DLL search path
    qt_bin = os.path.join(base, "PyQt5", "Qt5", "bin")
    if os.path.isdir(qt_bin):
        os.environ["PATH"] = qt_bin + os.pathsep + os.environ.get("PATH", "")
        os.add_dll_directory(qt_bin)
    # Also try top-level (some PyInstaller versions flatten DLLs here)
    os.add_dll_directory(base)
