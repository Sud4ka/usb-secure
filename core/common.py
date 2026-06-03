import hashlib
import logging
import os
import subprocess

import pyotp
import qrcode
from PIL import Image

logger = logging.getLogger(__name__)

TOTP_SECRET_FILE = ".usb_secure_totp"


class USBCryptorError(Exception):
    pass


def _find_executable(name: str) -> bool:
    return any(
        os.path.isfile(os.path.join(p, name)) and
        os.access(os.path.join(p, name), os.X_OK)
        for p in os.environ.get("PATH", "").split(os.pathsep)
        if p
    )


def _run(cmd: list[str], input_data: str | None = None,
         check: bool = True, timeout: int = 120,
         desc: str = "") -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd, input=input_data, capture_output=True,
            text=True, check=check, timeout=timeout
        )
    except subprocess.CalledProcessError as e:
        msg = (e.stderr or "").strip() or str(e)
        raise USBCryptorError(f"{desc}: {msg}" if desc else msg)
    except subprocess.TimeoutExpired:
        raise USBCryptorError(f"El comando tardó demasiado")
    except FileNotFoundError:
        raise USBCryptorError(f"No se encontró: {cmd[0]}")


def get_drive_id(device: str, serial: str = "") -> str:
    raw = serial or device
    return hashlib.md5(raw.encode()).hexdigest()[:8]


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def generate_qr_image(secret: str, label: str, size: int = 250):
    uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=label, issuer_name="USB Secure"
    )
    qr = qrcode.make(uri)
    qr = qr.resize((size, size), Image.Resampling.LANCZOS)
    return qr, uri


def verify_totp(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code, valid_window=1)
