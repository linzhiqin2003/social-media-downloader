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

# Now import and run the app
from src.main import app

if __name__ == "__main__":
    app()
