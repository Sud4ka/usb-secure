#!/usr/bin/env python3
"""
Build script for USB Secure.
Compila la aplicación en un ejecutable único con PyInstaller.

Uso:
    python build.py                     # Build para la plataforma actual
    python build.py --onefile           # Un solo archivo (default)
    python build.py --onedir            # Directorio con dependencias

Requiere: pip install pyinstaller
"""

import os
import platform
import shutil
import sys
from pathlib import Path

APP_NAME = "USB_Secure"
MAIN = "main.py"


def build():
    system = platform.system()
    dist = Path("dist")
    build_dir = Path("build")

    # Clean previous builds
    for d in [dist, build_dir]:
        if d.exists():
            shutil.rmtree(d)

    extra = []

    # Platform-specific options
    if system == "Windows":
        extra += ["--windowed"]
        icon = Path("icon.ico")
        if icon.exists():
            extra += ["--icon", str(icon)]
        # Windows: semicolon separator
        extra += ["--add-data", f"core{os.pathsep}core"]
        # On Windows we need to bundle VeraCrypt hint
    elif system == "Linux":
        icon = Path("icon.png")
        if icon.exists():
            extra += ["--icon", str(icon)]
        # Linux: colon separator
        extra += ["--add-data", f"core{os.pathsep}core"]
    else:
        extra += ["--add-data", f"core{os.pathsep}core"]

    # Detect if we should use --onefile or --onedir
    use_onefile = "--onedir" not in sys.argv
    if use_onefile:
        extra += ["--onefile"]
    else:
        extra += ["--onedir"]

    args = [
        MAIN,
        "--name", APP_NAME,
        "--clean",
        "--noconfirm",
        "--log-level", "INFO",
    ] + extra + [
        "--hidden-import", "customtkinter",
        "--hidden-import", "PIL",
        "--hidden-import", "PIL._tkinter_finder",
        "--hidden-import", "pyotp",
        "--hidden-import", "qrcode",
        "--hidden-import", "cryptography",
        "--hidden-import", "cryptography.hazmat.primitives.kdf.pbkdf2",
        "--collect-all", "customtkinter",
        "--collect-all", "PIL",
        "--collect-all", "cryptography",
        "--collect-all", "pyotp",
        "--collect-all", "qrcode",
        "--exclude-module", "tkinter.test",
        "--exclude-module", "unittest",
        "--exclude-module", "pdb",
    ]

    print(f"🔨  Building {APP_NAME} for {system}...")
    print(f"    {'One-file mode' if use_onefile else 'Directory mode'}")
    print()

    import PyInstaller.__main__
    PyInstaller.__main__.run(args)

    # Report result
    if system == "Windows":
        exe_name = f"{APP_NAME}.exe"
    else:
        exe_name = APP_NAME

    if use_onefile:
        result = dist / exe_name
        if result.exists():
            size_mb = result.stat().st_size / (1024 * 1024)
            print(f"\n✅  {exe_name} creado ({size_mb:.1f} MB)")
            print(f"    {result.resolve()}")
    else:
        result = dist / APP_NAME
        if result.exists():
            print(f"\n✅  Directorio creado: {result.resolve()}")

    print("\n💡  En Windows ejecute como Administrador.")
    print("    En Linux ejecute con: sudo -E ./" + exe_name)


if __name__ == "__main__":
    build()
