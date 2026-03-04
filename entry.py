#!/usr/bin/env python
"""Entry point for PyInstaller bundled executable."""

import sys
import os

# Ensure the src package can be imported
if getattr(sys, 'frozen', False):
    # Running as compiled
    bundle_dir = sys._MEIPASS
    sys.path.insert(0, bundle_dir)
else:
    # Running as script
    bundle_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, bundle_dir)


def main():
    """Launch GUI if --cli not passed, otherwise run CLI."""
    if "--cli" in sys.argv:
        sys.argv.remove("--cli")
        from src.main import app
        app()
    else:
        from src.gui import main as gui_main
        gui_main()


if __name__ == "__main__":
    main()
