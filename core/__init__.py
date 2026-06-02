"""
USB Secure - Core
=================
Cross-platform encryption + 2FA backend.
Auto-selects the platform backend (LUKS on Linux, VeraCrypt on Windows).
"""

import platform

from .common import (
    USBCryptorError,
    generate_totp_secret,
    generate_qr_image,
    verify_totp,
    get_drive_id,
    TOTP_SECRET_FILE,
)

_system = platform.system()

if _system == "Windows":
    from .windows import (
        list_usb_drives,
        encrypt_drive,
        unlock_drive,
        lock_drive,
        read_totp_secret,
        get_mount_point,
    )
    PLATFORM = "windows"
else:
    # Linux, macOS, BSD, etc.
    from .linux import (
        list_usb_drives,
        encrypt_drive,
        unlock_drive,
        lock_drive,
        read_totp_secret,
        get_mount_point,
    )
    PLATFORM = "linux"
