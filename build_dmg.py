#!/usr/bin/env python
"""Build macOS DMG installer."""

import os
import shutil
import subprocess
import sys
from pathlib import Path


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

    # Build .app bundle with PyInstaller
    print("\nBuilding .app bundle...")

    icon_path = project_root / "assets" / "icon.icns"
    # Convert ico to icns if needed
    if not icon_path.exists():
        ico_path = project_root / "assets" / "icon.ico"
        if ico_path.exists():
            print("Converting icon to icns format...")
            # Use sips to convert (macOS built-in)
            png_path = project_root / "assets" / "icon_512.png"
            subprocess.run([
                "sips", "-s", "format", "png",
                "-z", "512", "512",
                str(project_root / "assets" / "icon.png"),
                "--out", str(png_path)
            ], check=True)

            # Create iconset
            iconset_path = project_root / "assets" / "icon.iconset"
            iconset_path.mkdir(exist_ok=True)

            sizes = [16, 32, 64, 128, 256, 512]
            for size in sizes:
                subprocess.run([
                    "sips", "-z", str(size), str(size),
                    str(png_path),
                    "--out", str(iconset_path / f"icon_{size}x{size}.png")
                ], check=True)
                # Retina versions
                subprocess.run([
                    "sips", "-z", str(size*2), str(size*2),
                    str(png_path),
                    "--out", str(iconset_path / f"icon_{size}x{size}@2x.png")
                ], check=True)

            # Convert iconset to icns
            subprocess.run([
                "iconutil", "-c", "icns", str(iconset_path),
                "-o", str(icon_path)
            ], check=True)

            # Cleanup
            shutil.rmtree(iconset_path)
            png_path.unlink()
            print(f"Created: {icon_path}")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "Social Media Downloader",
        "--windowed",  # Creates .app bundle
        "--onedir",    # Better for .app
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
    ]

    if icon_path.exists():
        cmd.extend(["--icon", str(icon_path)])

    cmd.append("entry.py")

    subprocess.run(cmd, check=True)

    # Create DMG
    print("\nCreating DMG...")
    app_path = project_root / "dist" / "Social Media Downloader.app"
    dmg_path = project_root / "dist" / "SocialMediaDownloader-v1.0.0-macOS.dmg"

    if not app_path.exists():
        print(f"Error: {app_path} not found")
        sys.exit(1)

    # Remove old DMG if exists
    if dmg_path.exists():
        dmg_path.unlink()

    # Create DMG using hdiutil
    temp_dmg = project_root / "dist" / "temp.dmg"

    # Create a temporary directory for DMG contents
    dmg_contents = project_root / "dist" / "dmg_contents"
    if dmg_contents.exists():
        shutil.rmtree(dmg_contents)
    dmg_contents.mkdir()

    # Copy app to DMG contents
    shutil.copytree(app_path, dmg_contents / "Social Media Downloader.app")

    # Create Applications symlink
    os.symlink("/Applications", dmg_contents / "Applications")

    # Create DMG
    subprocess.run([
        "hdiutil", "create",
        "-volname", "Social Media Downloader",
        "-srcfolder", str(dmg_contents),
        "-ov",
        "-format", "UDZO",
        str(dmg_path)
    ], check=True)

    # Cleanup
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


if __name__ == "__main__":
    main()
