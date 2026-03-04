#!/usr/bin/env python
"""Build macOS .app bundle and DMG installer.

Since this is a terminal-based interactive app (uses input() and Rich),
we build a CLI binary and wrap it in a .app that auto-opens Terminal.
"""

import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path


APP_NAME = "Social Media Downloader"
VERSION = "1.2.0"


def main():
    """Build macOS .app bundle and DMG."""
    print("=" * 50)
    print("Building macOS DMG Installer")
    print("=" * 50)

    project_root = Path(__file__).parent
    os.chdir(project_root)

    # Clean previous builds
    for path in ["build", "dist", "smd.spec"]:
        if Path(path).exists():
            if Path(path).is_dir():
                shutil.rmtree(path)
            else:
                Path(path).unlink()
            print(f"Cleaned: {path}")

    # Step 1: Build CLI binary with PyInstaller
    print("\nBuilding CLI binary...")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "smd",
        "--console",
        "--collect-all", "httpx",
        "--collect-all", "typer",
        "--collect-all", "rich",
        "--collect-all", "pydantic",
        "--hidden-import", "src.xiaohongshu",
        "--hidden-import", "src.weibo",
        "--hidden-import", "src.xiaohongshu.downloader",
        "--hidden-import", "src.weibo.downloader",
        "--hidden-import", "src.app",
        "--hidden-import", "src.ui",
        "--add-data", "src:src",
        "entry.py",
    ]
    subprocess.run(cmd, check=True)

    smd_binary = project_root / "dist" / "smd"
    if not smd_binary.exists():
        print("[ERROR] Binary build failed")
        sys.exit(1)

    print(f"Binary built: {smd_binary} ({smd_binary.stat().st_size / 1024 / 1024:.1f} MB)")

    # Step 2: Create .app bundle
    print(f"\nCreating {APP_NAME}.app...")

    app_path = project_root / "dist" / f"{APP_NAME}.app"
    contents = app_path / "Contents"
    macos_dir = contents / "MacOS"
    resources_dir = contents / "Resources"

    for d in [macos_dir, resources_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # Copy binary into Resources
    shutil.copy2(smd_binary, resources_dir / "smd")

    # Create launcher script that opens Terminal
    launcher = macos_dir / "launcher"
    launcher.write_text(f"""#!/bin/bash
# Launcher for {APP_NAME}
# Opens Terminal.app and runs the interactive CLI

RESOURCES_DIR="$(cd "$(dirname "$0")/../Resources" && pwd)"
SMD_BIN="$RESOURCES_DIR/smd"

# Use AppleScript to open a new Terminal window and run smd
osascript <<APPLESCRIPT
tell application "Terminal"
    activate
    do script "clear && \\"$SMD_BIN\\"; exit"
end tell
APPLESCRIPT
""")
    launcher.chmod(0o755)

    # Create Info.plist
    info_plist = {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": "com.smd.social-media-downloader",
        "CFBundleVersion": VERSION,
        "CFBundleShortVersionString": VERSION,
        "CFBundleExecutable": "launcher",
        "CFBundlePackageType": "APPL",
        "CFBundleSignature": "????",
        "LSMinimumSystemVersion": "10.15",
        "NSHighResolutionCapable": True,
    }

    # Add icon if available
    icon_path = project_root / "assets" / "icon.icns"
    if not icon_path.exists():
        png_path = project_root / "assets" / "icon.png"
        if png_path.exists():
            print("Creating .icns from icon.png...")
            _create_icns(png_path, icon_path)

    if icon_path.exists():
        shutil.copy2(icon_path, resources_dir / "icon.icns")
        info_plist["CFBundleIconFile"] = "icon.icns"

    with open(contents / "Info.plist", "wb") as f:
        plistlib.dump(info_plist, f)

    print(f"Created: {app_path}")

    # Step 3: Create DMG
    print("\nCreating DMG...")
    dmg_path = project_root / "dist" / f"SocialMediaDownloader-v{VERSION}-macOS.dmg"

    if dmg_path.exists():
        dmg_path.unlink()

    dmg_contents = project_root / "dist" / "dmg_contents"
    if dmg_contents.exists():
        shutil.rmtree(dmg_contents)
    dmg_contents.mkdir()

    shutil.copytree(app_path, dmg_contents / f"{APP_NAME}.app")
    os.symlink("/Applications", dmg_contents / "Applications")

    subprocess.run([
        "hdiutil", "create",
        "-volname", APP_NAME,
        "-srcfolder", str(dmg_contents),
        "-ov",
        "-format", "UDZO",
        str(dmg_path)
    ], check=True)

    shutil.rmtree(dmg_contents)

    if dmg_path.exists():
        size_mb = dmg_path.stat().st_size / 1024 / 1024
        print("\n" + "=" * 50)
        print("[SUCCESS] DMG created!")
        print(f"File: {dmg_path}")
        print(f"Size: {size_mb:.1f} MB")
        print("=" * 50)
    else:
        print("\n[ERROR] DMG creation failed")
        sys.exit(1)


def _create_icns(png_path: Path, icns_path: Path):
    """Create .icns from a PNG file."""
    try:
        iconset_path = png_path.parent / "icon.iconset"
        iconset_path.mkdir(exist_ok=True)

        sizes = [16, 32, 64, 128, 256, 512]
        for size in sizes:
            subprocess.run([
                "sips", "-z", str(size), str(size),
                str(png_path), "--out",
                str(iconset_path / f"icon_{size}x{size}.png")
            ], check=True, capture_output=True)
            if size <= 256:
                subprocess.run([
                    "sips", "-z", str(size * 2), str(size * 2),
                    str(png_path), "--out",
                    str(iconset_path / f"icon_{size}x{size}@2x.png")
                ], check=True, capture_output=True)

        subprocess.run([
            "iconutil", "-c", "icns", str(iconset_path),
            "-o", str(icns_path)
        ], check=True, capture_output=True)

        shutil.rmtree(iconset_path)
    except Exception as e:
        print(f"Warning: Could not create .icns: {e}")


if __name__ == "__main__":
    main()
