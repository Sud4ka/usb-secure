import os
import json
import subprocess
import time
from pathlib import Path

from .common import (
    USBCryptorError, _run, get_drive_id,
    generate_totp_secret, generate_qr_image, verify_totp,
    TOTP_SECRET_FILE, logger,
)

MOUNT_BASE = "/media/usb-secure"
MAPPER_PREFIX = "usb-secure"


def is_luks(device: str) -> bool:
    try:
        r = _run(["cryptsetup", "isLuks", device], check=False, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def get_mapper_name(device: str) -> str:
    return f"{MAPPER_PREFIX}-{get_drive_id(device)}"


def get_mount_point(device: str) -> str:
    return f"{MOUNT_BASE}-{get_drive_id(device)}"


def list_usb_drives() -> list[dict]:
    drives = []
    try:
        result = subprocess.run(
            ["lsblk", "-J", "-o", "NAME,SIZE,TYPE,MOUNTPOINT,MODEL,VENDOR,TRAN"],
            capture_output=True, text=True, check=True, timeout=10
        )
        data = json.loads(result.stdout)

        def walk(items):
            for item in items:
                if item.get("tran") == "usb" and item.get("type") == "disk":
                    name = item["name"]
                    parts = item.get("children") or []
                    partitions = [f"/dev/{c['name']}" for c in parts if c.get("type") == "part"]
                    first_part = partitions[0] if partitions else None
                    target = first_part or f"/dev/{name}"
                    encrypted = is_luks(target)

                    info = {
                        "device": f"/dev/{name}",
                        "name": name,
                        "size": item.get("size", "Unknown"),
                        "model": item.get("model", "").strip(),
                        "vendor": item.get("vendor", "").strip(),
                        "partition": first_part,
                        "partitions": partitions,
                        "is_luks": encrypted,
                        "mountpoint": "",
                    }
                    for p in parts:
                        mp = p.get("mountpoint") or ""
                        if mp:
                            info["mountpoint"] = mp
                            break

                    mapper = get_mapper_name(f"/dev/{name}")
                    info["is_mapped"] = os.path.exists(f"/dev/mapper/{mapper}")
                    info["is_mounted"] = bool(info["mountpoint"]) or info["is_mapped"]
                    drives.append(info)

                kids = item.get("children")
                if kids:
                    walk(kids)

        walk(data.get("blockdevices", []))

    except subprocess.TimeoutExpired:
        raise USBCryptorError("Tiempo de espera agotado")
    except Exception as e:
        logger.error("Error listing drives: %s", e)
        raise USBCryptorError(f"No se pudieron listar las unidades: {e}")

    return drives


def encrypt_drive(device: str, password: str, progress_callback=None) -> dict:
    mapper = get_mapper_name(device)
    mpoint = get_mount_point(device)
    sudo_uid = os.environ.get("SUDO_UID", "0")
    sudo_gid = os.environ.get("SUDO_GID", "0")

    def cb(p, m):
        if progress_callback:
            progress_callback(p, m)

    cb(5, "Verificando dispositivo...")
    if not os.path.exists(device):
        raise USBCryptorError(f"El dispositivo {device} no existe")

    cb(10, "Limpiando dispositivo...")
    try:
        _run(["dd", "if=/dev/zero", f"of={device}", "bs=1M", "count=10"],
             desc="Limpiando", timeout=30)
    except USBCryptorError as e:
        raise USBCryptorError(f"Error al limpiar: {e}")

    cb(20, "Creando cifrado LUKS (AES-256-XTS)...")
    _run(
        ["cryptsetup", "-q", "luksFormat", "--type", "luks2",
         "--use-random", "--key-file=-", device],
        input_data=password + "\n", desc="Creando LUKS", timeout=60
    )

    cb(40, "Abriendo volumen cifrado...")
    _run(
        ["cryptsetup", "open", "--key-file=-", device, mapper],
        input_data=password + "\n", desc="Abriendo LUKS", timeout=10
    )

    try:
        cb(50, "Creando sistema de archivos ext4...")
        root_owner = f"{sudo_uid}:{sudo_gid}"
        _run(["mkfs.ext4", "-F", "-E", f"root_owner={root_owner}",
              f"/dev/mapper/{mapper}"],
             desc="Creando FS", timeout=60)

        cb(65, "Configurando autenticación 2FA (TOTP)...")
        totp_secret = generate_totp_secret()

        os.makedirs(mpoint, exist_ok=True)
        _run(["mount", f"/dev/mapper/{mapper}", mpoint],
             desc="Montando", timeout=10)

        try:
            _run(["chown", f"{sudo_uid}:{sudo_gid}", mpoint], check=False)
            _run(["chmod", "g+s", mpoint], check=False)
            Path(mpoint, TOTP_SECRET_FILE).write_text(totp_secret + "\n")
            Path(mpoint, "README.txt").write_text(
                "=== USB Secure - Unidad Cifrada ===\n\n"
                "Protegida con:\n"
                "1. Cifrado LUKS (AES-256-XTS)\n"
                "2. 2FA con TOTP (Google Authenticator)\n\n"
                "Use la aplicación USB Secure para acceder.\n"
            )
        finally:
            _run(["umount", mpoint], check=False)
    finally:
        cb(90, "Finalizando...")
        _run(["cryptsetup", "close", mapper], check=False)

    label = f"USB-Secure ({os.path.basename(device)})"
    qr_img, uri = generate_qr_image(totp_secret, label)

    cb(100, "¡Completado!")
    return {
        "totp_secret": totp_secret,
        "qr_image": qr_img,
        "uri": uri,
        "device": device,
        "mount_point": mpoint,
        "label": label,
    }


def read_totp_secret(device: str, password: str) -> str:
    mapper = get_mapper_name(device)
    mpoint = get_mount_point(device)

    _run(
        ["cryptsetup", "open", "--key-file=-", device, mapper],
        input_data=password + "\n",
        desc="Contraseña incorrecta o dispositivo inválido", timeout=10
    )
    try:
        os.makedirs(mpoint, exist_ok=True)
        _run(["mount", "-o", "ro", f"/dev/mapper/{mapper}", mpoint],
             desc="Error al montar", timeout=10)
        try:
            p = Path(mpoint, TOTP_SECRET_FILE)
            if not p.exists():
                raise USBCryptorError(
                    "No se encontró el archivo 2FA. ¿Unidad cifrada con USB Secure?"
                )
            return p.read_text().strip()
        finally:
            _run(["umount", mpoint], check=False)
    finally:
        _run(["cryptsetup", "close", mapper], check=False)


def unlock_drive(device: str, password: str, totp_code: str) -> str:
    mapper = get_mapper_name(device)
    mpoint = get_mount_point(device)
    mapper_path = f"/dev/mapper/{mapper}"

    os.makedirs(mpoint, exist_ok=True)

    if os.path.ismount(mpoint):
        raise USBCryptorError("La unidad ya está montada")
    if os.path.exists(mapper_path):
        raise USBCryptorError("El volumen ya está abierto")

    secret = read_totp_secret(device, password)
    if not verify_totp(secret, totp_code):
        raise USBCryptorError(
            "Código 2FA incorrecto. Verifique su aplicación autenticadora."
        )

    _run(
        ["cryptsetup", "open", "--key-file=-", device, mapper],
        input_data=password + "\n", desc="Error al abrir", timeout=10
    )

    for _ in range(50):
        if os.path.exists(mapper_path):
            break
        time.sleep(0.1)

    try:
        _run(["mount", f"/dev/mapper/{mapper}", mpoint],
             desc="Error al montar", timeout=10)
        sudo_uid = os.environ.get("SUDO_UID", "0")
        sudo_gid = os.environ.get("SUDO_GID", "0")
        _run(["chown", f"{sudo_uid}:{sudo_gid}", mpoint], check=False)
    except Exception:
        _run(["cryptsetup", "close", mapper], check=False)
        raise

    return mpoint


def lock_drive(device: str) -> bool:
    mapper = get_mapper_name(device)
    mpoint = get_mount_point(device)
    mapper_path = f"/dev/mapper/{mapper}"

    errors = []
    if os.path.ismount(mpoint):
        try:
            _run(["umount", mpoint], desc="Desmontando", timeout=10)
        except USBCryptorError as e:
            errors.append(str(e))

    if os.path.exists(mapper_path):
        try:
            _run(["cryptsetup", "close", mapper],
                 desc="Cerrando cifrado", timeout=10)
        except USBCryptorError as e:
            errors.append(str(e))

    if os.path.isdir(mpoint):
        try:
            os.rmdir(mpoint)
        except OSError:
            pass

    if errors:
        raise USBCryptorError(". ".join(errors))
    return True
