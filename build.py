#!/usr/bin/env python
"""Build script for creating executable with PyInstaller."""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    """Build the executable."""
    print("=" * 50)
    print("Social Media Downloader - Build Script")
    print("=" * 50)

    # Get project root
    project_root = Path(__file__).parent
    os.chdir(project_root)

    # Determine output name based on platform
    system = platform.system().lower()
    if system == "windows":
        exe_name = "smd.exe"
    else:
        exe_name = "smd"

    print(f"\nPlatform: {platform.system()}")
    print(f"Output: {exe_name}")

    # Clean previous builds
    for path in ["build", "dist", "smd.spec"]:
        if Path(path).exists():
            if Path(path).is_dir():
                shutil.rmtree(path)
            else:
                Path(path).unlink()
            print(f"Cleaned: {path}")

    # Install playwright browsers first
    print("\nInstalling Playwright browsers...")
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)

    # Get playwright browser path for bundling
    # Note: This is complex, so we'll use --collect-all instead

    # Build with PyInstaller
    print("\nBuilding executable...")

    # Check for icon
    icon_path = project_root / "assets" / "icon.ico"
    has_icon = icon_path.exists()
    if has_icon:
        print(f"Using icon: {icon_path}")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "smd",
        "--console",
        # Collect all required packages
        "--collect-all", "playwright",
        "--collect-all", "httpx",
        "--collect-all", "typer",
        "--collect-all", "rich",
        "--collect-all", "pydantic",
        # Hidden imports
        "--hidden-import", "src.xiaohongshu",
        "--hidden-import", "src.weibo",
        "--hidden-import", "src.xiaohongshu.downloader",
        "--hidden-import", "src.weibo.downloader",
        "--hidden-import", "src.app",
        "--hidden-import", "src.ui",
    ]

    # Add icon if available
    if has_icon:
        cmd.extend(["--icon", str(icon_path)])

    # Add src as data
    cmd.extend(["--add-data", "src:src"])

    # Entry point
    cmd.append("entry.py")

    subprocess.run(cmd, check=True)

    # Check if build succeeded
    dist_path = project_root / "dist" / exe_name
    if system != "windows":
        dist_path = project_root / "dist" / "smd"

    if dist_path.exists():
        print("\n" + "=" * 50)
        print(f"[SUCCESS] Build complete!")
        print(f"Executable: {dist_path}")
        print(f"Size: {dist_path.stat().st_size / 1024 / 1024:.1f} MB")
        print("=" * 50)

        print("\nIMPORTANT: Before running the executable, you need to:")
        print("1. Install Playwright browsers on the target machine:")
        print("   playwright install chromium")
        print("\nOr distribute with the browser bundled (see README).")
    else:
        print("\n[ERROR] Build failed - executable not found")
        sys.exit(1)


if __name__ == "__main__":
    main()
