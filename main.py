#!/usr/bin/env python3
"""
USB Secure - Cifrado de Pendrives con 2FA
=========================================
Multiplataforma: Linux (LUKS) y Windows (VeraCrypt).

Linux:
    sudo -E python3 main.py
Windows:
    python main.py  (ejecutar como Administrador)
"""

import os
import sys
import platform
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


def _fix_display():
    if os.geteuid() != 0:
        return
    if "DISPLAY" not in os.environ or not os.environ.get("DISPLAY"):
        os.environ["DISPLAY"] = os.environ.get("DISPLAY") or ":0"
    if "XAUTHORITY" not in os.environ or not os.environ.get("XAUTHORITY"):
        sudo_user = os.environ.get("SUDO_USER") or ""
        if sudo_user:
            for candidate in (
                f"/home/{sudo_user}/.Xauthority",
                f"/run/user/{os.environ.get('SUDO_UID', '1000')}/xauth",
                os.path.expanduser("~/.Xauthority"),
            ):
                if os.path.exists(candidate):
                    os.environ["XAUTHORITY"] = candidate
                    break


def _check_x_server():
    try:
        import tkinter
        root = tkinter.Tk()
        root.withdraw()
        root.destroy()
        return True
    except Exception as e:
        print("=" * 60)
        print("  ❌  No se puede conectar al servidor gráfico")
        if platform.system() == "Windows":
            print("  Asegúrese de ejecutar en una sesión de escritorio.")
        else:
            print()
            print("  Ejecute:  sudo -E python3 main.py")
            print("  Si falla: xhost +SI:localuser:root")
        print()
        print(f"  Detalle: {e}")
        print("=" * 60)
        return False


def _find_executable(name: str) -> bool:
    return any(
        os.path.isfile(os.path.join(p, name)) and
        os.access(os.path.join(p, name), os.X_OK)
        for p in os.environ.get("PATH", "").split(":")
        if p
    )


def _check_linux():
    """Check Linux-specific dependencies."""
    if os.geteuid() != 0 and platform.system() != "Windows":
        print("=" * 60)
        print("  ⚠️  En Linux debe ejecutar como root:")
        print("      sudo -E python3 main.py")
        print("=" * 60)
        sys.exit(1)

    missing = []
    for cmd in ["cryptsetup", "mkfs.ext4", "mount", "umount", "lsblk"]:
        if not _find_executable(cmd):
            missing.append(cmd)
    if missing:
        print("=" * 60)
        print("  ❌  Faltan herramientas del sistema Linux:")
        for cmd in missing:
            print(f"      - {cmd}")
        print()
        print("  Instálelas con:")
        print("      sudo apt install cryptsetup e2fsprogs mount util-linux")
        print("=" * 60)
        sys.exit(1)


def _check_windows():
    """Check Windows-specific dependencies (VeraCrypt)."""
    vc_paths = [
        r"C:\Program Files\VeraCrypt\VeraCrypt.exe",
        r"C:\Program Files (x86)\VeraCrypt\VeraCrypt.exe",
    ]
    found = any(os.path.exists(p) for p in vc_paths) or _find_executable("VeraCrypt.exe")
    if not found:
        print("=" * 60)
        print("  ❌  VeraCrypt no está instalado.")
        print()
        print("  Descárguelo desde:  https://www.veracrypt.fr")
        print("  E instálelo en la ubicación predeterminada.")
        print("=" * 60)
        sys.exit(1)


def check_privileges():
    """Check platform-appropriate privileges."""
    if platform.system() == "Windows":
        # On Windows, check if running as admin
        try:
            import ctypes
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
            if not is_admin:
                print("=" * 60)
                print("  ⚠️  Ejecute como Administrador")
                print("      (clic derecho > Ejecutar como administrador)")
                print("=" * 60)
                sys.exit(1)
        except Exception:
            pass  # Can't check, proceed anyway
    else:
        _check_linux()


def main():
    if platform.system() != "Windows":
        _fix_display()

    check_privileges()

    if platform.system() == "Windows":
        _check_windows()
    else:
        _check_linux()

    if not _check_x_server():
        sys.exit(1)

    import customtkinter as ctk
    from ui import App

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")

    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
