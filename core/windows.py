"""
Windows backend using VeraCrypt + PowerShell.

Requires: VeraCrypt installed at C:\\Program Files\\VeraCrypt\\
"""

import json
import os
import re
import time
import string
import subprocess
from pathlib import Path

from .common import (
    USBCryptorError, _run, get_drive_id, _find_executable,
    generate_totp_secret, generate_qr_image, verify_totp,
    TOTP_SECRET_FILE, logger,
)


VC_PATHS = [
    r"C:\Program Files\VeraCrypt\VeraCrypt.exe",
    r"C:\Program Files (x86)\VeraCrypt\VeraCrypt.exe",
]
VC_FMT_PATHS = [
    p.replace("VeraCrypt.exe", "VeraCrypt Format.exe") for p in VC_PATHS
]


def _vc():
    for p in VC_PATHS:
        if os.path.exists(p):
            return p
    if _find_executable("VeraCrypt.exe"):
        return "VeraCrypt.exe"
    raise USBCryptorError(
        "VeraCrypt no encontrado. Descárguelo de veracrypt.fr")


def _vc_run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a VeraCrypt command with user-friendly error messages."""
    try:
        return _run(cmd, **kwargs)
    except USBCryptorError as e:
        msg = _check_vc_error(str(e))
        if msg != str(e):
            raise USBCryptorError(msg)
        raise


def _check_vc_error(err: str) -> str:
    """Translate VeraCrypt error messages to user-friendly Spanish."""
    err_lower = err.lower()
    if "access is denied" in err_lower or "permission denied" in err_lower:
        return (
            "Permiso denegado por VeraCrypt.\n\n"
            "Ejecute USB Secure como Administrador\n"
            "(clic derecho > Ejecutar como administrador)\n\n"
            "O active en VeraCrypt:\n"
            "    Settings > System Integration >\n"
            "    Allow non-admin users to use VeraCrypt"
        )
    if "device" in err_lower and "not found" in err_lower:
        return f"Dispositivo no encontrado. Verifique la unidad."
    if "incorrect password" in err_lower or "wrong password" in err_lower:
        return "Contraseña incorrecta."
    return err


def _free_drive_letter(start: str = "U") -> str:
    """Return the first free drive letter from start backwards."""
    used = set()
    try:
        r = _run(["wmic", "logicaldisk", "get", "deviceid"],
                 timeout=5, check=False)
        used = set(re.findall(r"([A-Z]):", r.stdout.upper()))
    except Exception:
        pass
    for c in range(ord(start.upper()), ord("Z") + 1):
        letter = chr(c)
        if letter not in used:
            return f"{letter}:"
    for c in range(ord("D"), ord(start.upper())):
        letter = chr(c)
        if letter not in used:
            return f"{letter}:"
    raise USBCryptorError("No hay letras de unidad libres")


def get_mount_point(device: str) -> str:
    """On Windows the 'mount point' is a drive letter stored by device id."""
    # We store a mapping from device serial to drive letter
    return _free_drive_letter()


def list_usb_drives() -> list[dict]:
    drives = []
    try:
        ps = (
            "Get-WmiObject Win32_LogicalDisk -Filter \"DriveType=2\" | "
            "Select DeviceID, VolumeName, Size, FileSystem, "
            "@{N='SizeGB';E={[math]::Round($_.Size/1GB,1)}} | "
            "ConvertTo-Json"
        )
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=15
        )
        data = json.loads(r.stdout) if r.stdout.strip() else []
        if isinstance(data, dict):
            data = [data]

        # Check VeraCrypt mounted volumes
        vc_vols = _vc_list()

        for item in data:
            device = item.get("DeviceID", "")
            if not device:
                continue
            letter = device.rstrip(":\\")
            is_vc = device in vc_vols

            drive = {
                "device": device,
                "name": letter,
                "size": f"{item.get('SizeGB', 0)} GB",
                "model": item.get("VolumeName", "USB Drive"),
                "vendor": "USB",
                "partition": device,
                "partitions": [device],
                "is_luks": is_vc,
                "is_mapped": is_vc,
                "is_mounted": is_vc,
                "mountpoint": device if is_vc else "",
            }
            drives.append(drive)
    except Exception as e:
        logger.error("Error listing drives: %s", e)
        raise USBCryptorError(f"No se pudieron listar las unidades: {e}")
    return drives


def _vc_list() -> set[str]:
    """Return set of drive letters where VeraCrypt volumes are mounted."""
    result = set()
    try:
        r = subprocess.run(
            [_vc(), "/list"], capture_output=True, text=True, timeout=10
        )
        for line in r.stdout.splitlines():
            m = re.match(r"^\d+:\s+([A-Z]:)", line.strip())
            if m:
                result.add(m.group(1))
    except Exception:
        pass
    return result


def is_encrypted(device: str) -> bool:
    """Check if a device/path has a VeraCrypt volume signature."""
    try:
        r = subprocess.run(
            [_vc(), "/volume", device, "/properties"],
            capture_output=True, text=True, timeout=10
        )
        return "VeraCrypt" in r.stdout or r.returncode == 0
    except Exception:
        return False


def encrypt_drive(device: str, password: str, progress_callback=None) -> dict:
    """Create a VeraCrypt volume on a USB drive."""
    vc = _vc()

    def cb(p, m):
        if progress_callback:
            progress_callback(p, m)

    # Map device like "G:" to the physical drive path for VeraCrypt
    cb(10, "Verificando dispositivo...")
    if not os.path.exists(device):
        raise USBCryptorError(f"La unidad {device} no existe")

    cb(20, "Creando volumen VeraCrypt (AES-256)...")
    # VeraCrypt Format creates the volume; we use the main exe with /create
    _vc_run(
        [vc, "/create", device,
         "/encryption", "AES", "/hash", "SHA-256",
         "/filesystem", "exFAT",
         "/password", password,
         "/silent"],
        desc="Creando volumen VeraCrypt", timeout=180
    )

    cb(40, "Abriendo volumen cifrado...")
    letter = get_mount_point(device)
    _vc_run(
        [vc, "/mount", device, "/letter", letter.rstrip(":"),
         "/password", password, "/silent"],
        desc="Montando volumen", timeout=15
    )

    try:
        cb(50, "Formateando...")
        time.sleep(1)  # Wait for mount

        cb(65, "Configurando autenticación 2FA (TOTP)...")
        totp_secret = generate_totp_secret()

        secret_path = Path(f"{letter}\\{TOTP_SECRET_FILE}")
        secret_path.write_text(totp_secret + "\n")
        Path(f"{letter}\\README.txt").write_text(
            "=== USB Secure - Unidad Cifrada ===\n\n"
            "Protegida con:\n"
            "1. Cifrado VeraCrypt (AES-256)\n"
            "2. 2FA con TOTP (Google Authenticator)\n\n"
            "Use la aplicación USB Secure para acceder.\n"
        )
    finally:
        cb(90, "Finalizando...")
        _vc_run([vc, "/dismount", device, "/silent"], check=False)

    label = f"USB-Secure ({os.path.basename(device)})"
    qr_img, uri = generate_qr_image(totp_secret, label)

    cb(100, "¡Completado!")
    return {
        "totp_secret": totp_secret,
        "qr_image": qr_img,
        "uri": uri,
        "device": device,
        "mount_point": letter,
        "label": label,
    }


def read_totp_secret(device: str, password: str) -> str:
    vc = _vc()
    letter = _free_drive_letter()

    _vc_run(
        [vc, "/mount", device, "/letter", letter.rstrip(":"),
         "/password", password, "/silent"],
        desc="Contraseña incorrecta", timeout=15
    )
    try:
        p = Path(f"{letter}\\{TOTP_SECRET_FILE}")
        if not p.exists():
            raise USBCryptorError(
                "No se encontró el archivo 2FA. ¿Unidad cifrada con USB Secure?"
            )
        return p.read_text().strip()
    finally:
        _vc_run([vc, "/dismount", device, "/silent"], check=False)


def unlock_drive(device: str, password: str, totp_code: str) -> str:
    vc = _vc()
    letter = _free_drive_letter()

    if device in _vc_list():
        raise USBCryptorError("La unidad ya está montada")

    secret = read_totp_secret(device, password)
    if not verify_totp(secret, totp_code):
        raise USBCryptorError(
            "Código 2FA incorrecto. Verifique su aplicación autenticadora."
        )

    _vc_run(
        [vc, "/mount", device, "/letter", letter.rstrip(":"),
         "/password", password, "/silent"],
        desc="Error al abrir el volumen", timeout=15
    )
    return f"{letter}\\"


def lock_drive(device: str) -> bool:
    vc = _vc()
    _vc_run([vc, "/dismount", device, "/silent"],
            desc="Error al cerrar el volumen", timeout=10)
    return True
