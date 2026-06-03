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
import traceback

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


def _fix_path():
    """Ensure system sbin dirs are in PATH (lost in some PyInstaller builds)."""
    for d in ("/sbin", "/usr/sbin", "/usr/local/sbin"):
        if d not in os.environ.get("PATH", "").split(os.pathsep):
            os.environ["PATH"] = f'{os.environ.get("PATH", "")}{os.pathsep}{d}'


def _fix_display():
    if os.geteuid() != 0:
        return
    if "WAYLAND_DISPLAY" in os.environ and os.environ.get("WAYLAND_DISPLAY"):
        sudo_uid = os.environ.get("SUDO_UID") or ""
        if sudo_uid and not os.environ.get("XDG_RUNTIME_DIR"):
            candidate = f"/run/user/{sudo_uid}"
            if os.path.isdir(candidate):
                os.environ["XDG_RUNTIME_DIR"] = candidate
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


def _show_error(msg: str):
    """Show error to user and exit."""
    if platform.system() == "Windows":
        try:
            import tkinter.messagebox as mb
            mb.showerror("USB Secure - Error", msg)
        except Exception:
            print(f"ERROR: {msg}", file=sys.stderr)
    else:
        print("=" * 60)
        for line in msg.split("\n"):
            print(f"  {line}")
        print("=" * 60)
    sys.exit(1)


def _check_x_server():
    try:
        import tkinter
        root = tkinter.Tk()
        root.withdraw()
        root.update()
        root.destroy()
        return True
    except Exception as e:
        msg = "No se puede conectar al servidor gráfico.\n\n" f"Detalle: {e}"
        if platform.system() == "Windows":
            msg += "\n\nAsegúrese de ejecutar en una sesión de escritorio."
        else:
            msg += (
                "\n\nEjecute:\n    sudo -E python3 main.py\n"
                "Si falla:\n    xhost +SI:localuser:root\n"
                "En Wayland:\n    ~/.local/bin/usb-secure"
            )
        _show_error(msg)


def _find_executable(name: str) -> bool:
    return any(
        os.path.isfile(os.path.join(p, name))
        and os.access(os.path.join(p, name), os.X_OK)
        for p in os.environ.get("PATH", "").split(os.pathsep)
        if p
    )


def _check_linux():
    if os.geteuid() != 0:
        _show_error("En Linux debe ejecutar como root:\n    sudo -E python3 main.py")

    missing = []
    for cmd in ["cryptsetup", "mkfs.ext4", "mount", "umount", "lsblk"]:
        if not _find_executable(cmd):
            missing.append(cmd)
    if missing:
        _show_error(
            "Faltan herramientas del sistema Linux:\n"
            + "\n".join(f"    - {cmd}" for cmd in missing)
            + "\n\nInstálelas con:\n"
            "    sudo apt install cryptsetup e2fsprogs mount util-linux"
        )


def _check_windows():
    vc_paths = [
        r"C:\Program Files\VeraCrypt\VeraCrypt.exe",
        r"C:\Program Files (x86)\VeraCrypt\VeraCrypt.exe",
    ]
    found = (
        any(os.path.exists(p) for p in vc_paths)
        or _find_executable("VeraCrypt.exe")
    )
    if not found:
        _show_error(
            "VeraCrypt no está instalado.\n\n"
            "Descárguelo desde:\n"
            "    https://www.veracrypt.fr\n"
            "E instálelo en la ubicación predeterminada."
        )


def check_privileges():
    if platform.system() != "Windows":
        _check_linux()


def main():
    sys.excepthook = lambda etype, value, tb: (
        logging.error(
            "Unhandled:\n%s",
            "".join(traceback.format_exception(etype, value, tb)),
        )
        or (
            _show_error(f"Error inesperado:\n{value}")
            if platform.system() == "Windows"
            else None
        )
    )

    if platform.system() != "Windows":
        _fix_path()
        _fix_display()

    check_privileges()

    if platform.system() == "Windows":
        _check_windows()
    else:
        _check_linux()

    _check_x_server()

    import customtkinter as ctk
    from ui import App

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")

    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
