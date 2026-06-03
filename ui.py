import os
import sys
import subprocess
import threading
import platform
import tkinter.messagebox as mb
from pathlib import Path

import customtkinter as ctk

from core import (
    list_usb_drives, encrypt_drive, unlock_drive, lock_drive,
    read_totp_secret, generate_qr_image, USBCryptorError,
    get_mount_point, PLATFORM,
)

_IS_WINDOWS = platform.system() == "Windows"

SELECTED_COLOR = "#1a3a5c"
ACCENT = "#2980b9"


class DriveCard(ctk.CTkFrame):
    def __init__(self, master, drive_info, on_select, on_double_click=None):
        super().__init__(master, corner_radius=8, border_width=1,
                         border_color="gray30", fg_color="transparent")
        self.drive = drive_info
        self.on_select = on_select
        self.on_double_click = on_double_click
        self.selected = False

        icon = "🔒" if drive_info["is_luks"] else "💽"
        if drive_info.get("is_mapped"):
            icon = "🔓"

        name = drive_info['name'] if _IS_WINDOWS else f"/dev/{drive_info['name']}"
        extra = f" - {drive_info['vendor']} {drive_info['model']}".strip()
        if not extra.strip("- "):
            extra = ""

        info = ctk.CTkFrame(self, fg_color="transparent")
        info.pack(fill="x", expand=True, padx=12, pady=8)

        ctk.CTkLabel(
            info, text=f"{icon}  {name}{extra}",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w")

        sub = f"Tamaño: {drive_info['size']}"
        if drive_info["is_luks"]:
            sub += "  |  Cifrado: LUKS + TOTP 2FA"
        if drive_info.get("is_mapped"):
            sub += "  |  🔓 Abierto"
        if drive_info.get("mountpoint"):
            sub += f"  |  📁 {drive_info['mountpoint']}"

        ctk.CTkLabel(
            info, text=sub,
            font=ctk.CTkFont(size=11), text_color="gray60"
        ).pack(anchor="w")

        self._bind_click(self)

    def _bind_click(self, w):
        w.bind("<Button-1>", self._click, add="+")
        w.bind("<Double-Button-1>", self._double_click, add="+")
        for c in w.winfo_children():
            self._bind_click(c)

    def _click(self, _=None):
        for w in self.master.winfo_children():
            if isinstance(w, DriveCard) and w.selected:
                w._deselect()
        self._select()
        if self.on_select:
            self.on_select(self.drive)

    def _double_click(self, _=None):
        # Select first, then trigger action
        self._click()
        if self.on_double_click:
            self.on_double_click(self.drive)

    def _select(self):
        self.selected = True
        self.configure(fg_color=SELECTED_COLOR, border_color=ACCENT)

    def _deselect(self):
        self.selected = False
        self.configure(fg_color="transparent", border_color="gray30")


class QRDialog(ctk.CTkToplevel):
    def __init__(self, master, qr_image, secret, label, uri):
        super().__init__(master)
        self.title("📱 Configurar Autenticación 2FA")
        self.geometry("480x580")
        self.resizable(False, False)
        self.transient(master)

        ctk.CTkLabel(
            self, text="Escanea este código con tu app de autenticación",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(20, 5))

        ctk.CTkLabel(
            self, text="Google Authenticator, Authy, etc.",
            text_color="gray60", font=ctk.CTkFont(size=11)
        ).pack(pady=(0, 15))

        ctk.CTkLabel(
            self, text=label,
            text_color=ACCENT, font=ctk.CTkFont(size=12)
        ).pack()

        ctk_image = ctk.CTkImage(
            dark_image=qr_image, light_image=qr_image, size=(240, 240)
        )
        ctk.CTkLabel(self, image=ctk_image, text="").pack(pady=10)

        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(pady=5)

        ctk.CTkLabel(
            frame, text="Clave secreta (ingreso manual):",
            font=ctk.CTkFont(size=11)
        ).pack()

        secret_frame = ctk.CTkFrame(frame, fg_color="gray17", corner_radius=6)
        secret_frame.pack(fill="x", padx=30, pady=5)

        s = " ".join(secret[i:i+4] for i in range(0, len(secret), 4))
        ctk.CTkLabel(
            secret_frame, text=s,
            font=ctk.CTkFont(size=13, family="Courier"),
            text_color="#2ecc71"
        ).pack(pady=6)

        ctk.CTkButton(
            self, text="✅  Listo, ya escaneé el código",
            command=self.destroy, fg_color="green", hover_color="#27ae60",
            width=250
        ).pack(pady=15)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._closed = False

    def _on_close(self):
        self._closed = True
        self.destroy()

    def was_closed(self):
        return self._closed


class EncryptDialog(ctk.CTkToplevel):
    def __init__(self, master, drive):
        super().__init__(master)
        self.drive = drive
        self.result = None
        self.title("🔒 Cifrar Unidad")
        self.geometry("520x400")
        self.resizable(False, False)
        self.transient(master)

        self._build_password_ui()

    def _build_password_ui(self):
        self.password_frame = ctk.CTkFrame(self)
        self.password_frame.pack(fill="both", expand=True, padx=25, pady=20)

        ctk.CTkLabel(
            self.password_frame,
            text=f"Dispositivo: {self.drive['device']}  ({self.drive['size']})",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", pady=(0, 5))

        warning = ctk.CTkFrame(self.password_frame, fg_color="#3d1a1a",
                               corner_radius=6)
        warning.pack(fill="x", pady=(0, 15))
        ctk.CTkLabel(
            warning,
            text="⚠️  TODOS LOS DATOS EXISTENTES SERÁN BORRADOS",
            text_color="#e74c3c", font=ctk.CTkFont(size=12, weight="bold")
        ).pack(pady=6)

        ctk.CTkLabel(
            self.password_frame, text="Contraseña de cifrado:",
            font=ctk.CTkFont(size=12)
        ).pack(anchor="w")

        self.pw1 = ctk.CTkEntry(self.password_frame, show="*", placeholder_text="Mínimo 8 caracteres")
        self.pw1.pack(fill="x", pady=(3, 10))

        ctk.CTkLabel(
            self.password_frame, text="Confirmar contraseña:",
            font=ctk.CTkFont(size=12)
        ).pack(anchor="w")

        self.pw2 = ctk.CTkEntry(self.password_frame, show="*", placeholder_text="Repita la contraseña")
        self.pw2.pack(fill="x", pady=(3, 15))

        btn_frame = ctk.CTkFrame(self.password_frame, fg_color="transparent")
        btn_frame.pack(fill="x")

        ctk.CTkButton(
            btn_frame, text="Cancelar", command=self.destroy,
            width=120
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            btn_frame, text="🔒  Cifrar Unidad",
            command=self._start_encrypt,
            fg_color="#c0392b", hover_color="#e74c3c",
            width=160
        ).pack(side="right", padx=5)

    def _start_encrypt(self):
        p1, p2 = self.pw1.get(), self.pw2.get()
        if len(p1) < 8:
            self._status(self.password_frame, "La contraseña debe tener al menos 8 caracteres", "red")
            return
        if p1 != p2:
            self._status(self.password_frame, "Las contraseñas no coinciden", "red")
            return

        self.password_frame.pack_forget()
        self._build_progress_ui()

        t = threading.Thread(target=self._do_encrypt, args=(p1,), daemon=True)
        t.start()

    def _build_progress_ui(self):
        self.progress_frame = ctk.CTkFrame(self)
        self.progress_frame.pack(fill="both", expand=True, padx=25, pady=30)

        ctk.CTkLabel(
            self.progress_frame, text="Cifrando unidad...",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=(0, 15))

        self.progress_bar = ctk.CTkProgressBar(self.progress_frame, width=400)
        self.progress_bar.pack(pady=10)
        self.progress_bar.set(0)

        self.progress_label = ctk.CTkLabel(
            self.progress_frame, text="Iniciando...",
            font=ctk.CTkFont(size=12)
        )
        self.progress_label.pack(pady=5)

        self.progress_percent = ctk.CTkLabel(
            self.progress_frame, text="0%",
            font=ctk.CTkFont(size=11), text_color="gray60"
        )
        self.progress_percent.pack()

    def _update_progress(self, pct, msg):
        self.progress_bar.set(pct / 100)
        self.progress_label.configure(text=msg)
        self.progress_percent.configure(text=f"{pct}%")

    def _do_encrypt(self, password):
        try:
            result = encrypt_drive(
                self.drive["device"], password, self._update_progress
            )
            self.result = result
            self.after(0, self._show_qr)
        except USBCryptorError as e:
            self.after(0, self._show_error, str(e))
        except Exception as e:
            self.after(0, self._show_error, f"Error inesperado: {e}")

    def _show_qr(self):
        for w in self.progress_frame.winfo_children():
            w.destroy()
        self.progress_frame.pack_forget()

        if self.result:
            qr = QRDialog(self, self.result["qr_image"],
                          self.result["totp_secret"],
                          self.result["label"],
                          self.result["uri"])

            def check_closed():
                if qr.was_closed():
                    self.destroy()
                else:
                    self.after(500, check_closed)

            self.after(500, check_closed)

    def _show_error(self, msg):
        for w in self.progress_frame.winfo_children():
            w.destroy()
        self.progress_frame.pack_forget()

        frame = ctk.CTkFrame(self)
        frame.pack(fill="both", expand=True, padx=25, pady=30)

        ctk.CTkLabel(
            frame, text="❌  Error",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#e74c3c"
        ).pack(pady=(20, 10))

        ctk.CTkLabel(
            frame, text=msg, wraplength=450,
            font=ctk.CTkFont(size=12)
        ).pack(pady=10)

        ctk.CTkButton(frame, text="Cerrar", command=self.destroy).pack(pady=15)

    def _status(self, parent, msg, color="yellow"):
        for w in parent.winfo_children():
            if isinstance(w, ctk.CTkLabel) and w.cget("text").startswith(("⚠", "La", "Las")):
                w.destroy()
        ctk.CTkLabel(
            parent, text=msg, text_color=color,
            font=ctk.CTkFont(size=11)
        ).pack(anchor="w", pady=(0, 5))


class UnlockDialog(ctk.CTkToplevel):
    def __init__(self, master, drive):
        super().__init__(master)
        self.drive = drive
        self.title("🔓 Abrir Unidad")
        self.geometry("420x350")
        self.resizable(False, False)
        self.transient(master)

        frame = ctk.CTkFrame(self)
        frame.pack(fill="both", expand=True, padx=25, pady=20)

        ctk.CTkLabel(
            frame, text=f"Dispositivo: {drive['device']}",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", pady=(0, 15))

        ctk.CTkLabel(frame, text="Contraseña de cifrado:",
                     font=ctk.CTkFont(size=12)).pack(anchor="w")
        self.pw_entry = ctk.CTkEntry(frame, show="*")
        self.pw_entry.pack(fill="x", pady=(3, 12))

        ctk.CTkLabel(
            frame, text="Código 2FA (Google Authenticator):",
            font=ctk.CTkFont(size=12)
        ).pack(anchor="w")
        self.totp_entry = ctk.CTkEntry(
            frame, placeholder_text="000000",
            font=ctk.CTkFont(size=16, family="Courier")
        )
        self.totp_entry.pack(fill="x", pady=(3, 5))
        self.totp_entry.configure(width=120)

        self.status = ctk.CTkLabel(
            frame, text="",
            font=ctk.CTkFont(size=11), text_color="gray70"
        )
        self.status.pack(pady=(5, 0))

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(15, 0))

        ctk.CTkButton(
            btn_frame, text="Cancelar", command=self.destroy,
            width=100
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            btn_frame, text="🔓  Desbloquear",
            command=self._do_unlock,
            fg_color="#27ae60", hover_color="#2ecc71",
            width=140
        ).pack(side="right", padx=5)

        self.pw_entry.focus()

    def _do_unlock(self):
        pw = self.pw_entry.get()
        code = self.totp_entry.get().strip()

        if not pw:
            self.status.configure(text="Ingrese la contraseña", text_color="#f39c12")
            return
        if len(code) < 6:
            self.status.configure(text="Ingrese el código 2FA de 6 dígitos", text_color="#f39c12")
            return

        self.status.configure(text="🔄 Verificando...", text_color="gray70")
        self._disable_buttons()

        t = threading.Thread(target=self._unlock_thread, args=(pw, code), daemon=True)
        t.start()

    def _disable_buttons(self):
        for w in self.winfo_children():
            for c in w.winfo_children():
                if isinstance(c, ctk.CTkButton):
                    c.configure(state="disabled")

    def _enable_buttons(self):
        for w in self.winfo_children():
            for c in w.winfo_children():
                if isinstance(c, ctk.CTkButton):
                    c.configure(state="normal")

    def _unlock_thread(self, password, code):
        try:
            mpoint = unlock_drive(self.drive["device"], password, code)
            self.after(0, self._show_success, mpoint)
        except USBCryptorError as e:
            self.after(0, self._show_error, str(e))
        except Exception as e:
            self.after(0, self._show_error, f"Error inesperado: {e}")

    def _show_success(self, mpoint):
        for w in self.winfo_children():
            w.destroy()

        frame = ctk.CTkFrame(self)
        frame.pack(fill="both", expand=True, padx=25, pady=30)

        ctk.CTkLabel(
            frame, text="✅  Unidad Desbloqueada",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#2ecc71"
        ).pack(pady=(20, 10))

        ctk.CTkLabel(
            frame, text=f"Montada en:",
            font=ctk.CTkFont(size=12), text_color="gray60"
        ).pack()

        ctk.CTkLabel(
            frame, text=mpoint,
            font=ctk.CTkFont(size=14, weight="bold", family="Courier"),
            text_color=ACCENT
        ).pack(pady=3)

        ctk.CTkButton(
            frame, text="📂  Abrir Carpeta",
            command=lambda: self._open_folder(mpoint),
            width=180
        ).pack(pady=10)

        ctk.CTkButton(
            frame, text="Cerrar", command=self._on_close,
            width=120
        ).pack(pady=5)

        self._success = True

    def _on_close(self):
        if hasattr(self, "_success") and self._success:
            if self.master and hasattr(self.master, "_refresh_drives"):
                self.master._refresh_drives()
        self.destroy()

    def _open_folder(self, path):
        if _IS_WINDOWS:
            os.startfile(path)
            return
        user = os.environ.get("SUDO_USER") or os.environ.get("USER")
        if user:
            subprocess.Popen(["sudo", "-u", user, "xdg-open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    def _show_error(self, msg):
        self._enable_buttons()
        self.status.configure(text=f"❌  {msg}", text_color="#e74c3c")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("🔐 USB Secure - Cifrado de Pendrives")
        self.geometry("780x580")
        self.minsize(680, 450)

        self.drives = []
        self.selected_drive = None
        self._refreshing = False

        self._build_ui()
        self._refresh_drives()
        self._start_auto_refresh()

    def _build_ui(self):
        # Title
        title = ctk.CTkFrame(self, corner_radius=0, fg_color="gray17")
        title.pack(fill="x")
        ctk.CTkLabel(
            title,
            text="🔐  USB Secure",
            font=ctk.CTkFont(size=26, weight="bold")
        ).pack(pady=(16, 2))
        ctk.CTkLabel(
            title,
            text="Cifrado LUKS + Autenticación 2FA (TOTP) para Pendrives",
            font=ctk.CTkFont(size=11), text_color="gray50"
        ).pack(pady=(0, 12))

        # Content
        content = ctk.CTkFrame(self)
        content.pack(fill="both", expand=True, padx=15, pady=(8, 0))

        # Header
        hdr = ctk.CTkFrame(content, fg_color="transparent")
        hdr.pack(fill="x", pady=(5, 8))

        ctk.CTkLabel(
            hdr, text="📀  Unidades Detectadas",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left")

        ctk.CTkButton(
            hdr, text="⟳  Refrescar", width=110,
            command=self._refresh_drives
        ).pack(side="right")

        # Drive list
        self.scroll = ctk.CTkScrollableFrame(content)
        self.scroll.pack(fill="both", expand=True)

        # Bottom actions
        acts = ctk.CTkFrame(self)
        acts.pack(fill="x", padx=15, pady=(8, 10))

        self.btn_encrypt = ctk.CTkButton(
            acts, text="🔒  Cifrar", state="disabled",
            command=self._show_encrypt, width=130
        )
        self.btn_encrypt.pack(side="left", padx=4)

        self.btn_unlock = ctk.CTkButton(
            acts, text="🔓  Abrir", state="disabled",
            command=self._show_unlock, width=130
        )
        self.btn_unlock.pack(side="left", padx=4)

        self.btn_eject = ctk.CTkButton(
            acts, text="⏏  Expulsar", state="disabled",
            fg_color="#7f0000", hover_color="#a00000",
            command=self._eject, width=130
        )
        self.btn_eject.pack(side="left", padx=4)

        ctk.CTkButton(
            acts, text="📱  Código QR", state="disabled",
            command=self._show_qr_recovery, width=130
        ).pack(side="right", padx=4)
        self.btn_qr = acts.winfo_children()[-1]

        # Status bar
        self.status_bar = ctk.CTkFrame(self, corner_radius=0, height=28, fg_color="gray17")
        self.status_bar.pack(fill="x", side="bottom")
        self.status = ctk.CTkLabel(
            self.status_bar, text="💀  Listo",
            anchor="w", font=ctk.CTkFont(size=11)
        )
        self.status.pack(side="left", padx=10)

    def _start_auto_refresh(self):
        def loop():
            while True:
                import time
                time.sleep(4)
                if not self._refreshing:
                    self.after(0, self._refresh_drives)
        t = threading.Thread(target=loop, daemon=True)
        t.start()

    def _refresh_drives(self):
        if self._refreshing:
            return
        self._refreshing = True
        self.status.configure(text="🔄  Escaneando dispositivos...")

        def do_refresh():
            try:
                drives = list_usb_drives()
                self.after(0, self._update_list, drives)
            except Exception as e:
                self.after(0, lambda: self.status.configure(text=f"❌  {e}"))
            finally:
                self._refreshing = False

        t = threading.Thread(target=do_refresh, daemon=True)
        t.start()

    def _update_list(self, drives):
        # Preserve selection if device still exists in new list
        prev_device = self.selected_drive["device"] if self.selected_drive else None

        for w in self.scroll.winfo_children():
            w.destroy()
        self.drives = drives
        self.selected_drive = None
        self._update_buttons()

        if not drives:
            ctk.CTkLabel(
                self.scroll,
                text="No se detectaron unidades USB.\n\nConecte un pendrive y presione 'Refrescar'.",
                font=ctk.CTkFont(size=13), text_color="gray50"
            ).pack(pady=50)
            self.status.configure(text="💀  Sin dispositivos")
            return

        for d in drives:
            card = DriveCard(self.scroll, d, self._on_select, self._on_double_click)
            card.pack(fill="x", padx=5, pady=3)
            if prev_device and d["device"] == prev_device:
                card._click()

        self.status.configure(text=f"💀  {len(drives)} unidad(es) detectada(s)")

    def _on_select(self, drive):
        self.selected_drive = drive
        self._update_buttons()

    def _on_double_click(self, drive):
        """Double-click: unlock if encrypted, open folder if mounted, encrypt if raw."""
        if drive.get("is_mapped") or drive.get("is_mounted"):
            self._open_drive_folder()
        elif drive["is_luks"]:
            self._show_unlock()
        else:
            self._show_encrypt()

    def _open_drive_folder(self):
        drive = self.selected_drive
        if not drive:
            return
        mpoint = get_mount_point(drive["device"])
        if os.path.isdir(mpoint):
            if _IS_WINDOWS:
                os.startfile(mpoint)
                return
            user = os.environ.get("SUDO_USER") or os.environ.get("USER")
            if user:
                subprocess.Popen(["sudo", "-u", user, "xdg-open", mpoint])
            else:
                subprocess.Popen(["xdg-open", mpoint])

    def _update_buttons(self):
        d = self.selected_drive
        if not d:
            self.btn_encrypt.configure(state="disabled")
            self.btn_unlock.configure(state="disabled", text="🔓  Abrir")
            self.btn_eject.configure(state="disabled")
            self.btn_qr.configure(state="disabled")
            return

        mapped = d.get("is_mapped") or d.get("is_mounted")

        self.btn_encrypt.configure(state="normal" if not d["is_luks"] else "disabled")

        if mapped:
            self.btn_unlock.configure(state="normal", text="📂  Abrir Carpeta",
                                      command=self._open_drive_folder, fg_color="#2c3e50",
                                      hover_color="#34495e")
        else:
            self.btn_unlock.configure(
                state="normal" if d["is_luks"] else "disabled",
                text="🔓  Abrir", command=self._show_unlock,
                fg_color="#27ae60", hover_color="#2ecc71")

        self.btn_eject.configure(state="normal" if mapped else "disabled")
        self.btn_qr.configure(state="normal" if d["is_luks"] else "disabled")

    def _show_encrypt(self):
        drive = self.selected_drive
        if not drive:
            return
        if not mb.askyesno(
            "Confirmar",
            f"¿Está seguro de cifrar {drive['device']}?\n\n"
            "TODOS los datos existentes serán borrados permanentemente."
        ):
            return
        EncryptDialog(self, drive)

    def _show_unlock(self):
        drive = self.selected_drive
        if not drive:
            return
        UnlockDialog(self, drive)

    def _show_qr_recovery(self):
        drive = self.selected_drive
        if not drive:
            return

        class RecoveryDialog(ctk.CTkToplevel):
            def __init__(self, master, device):
                super().__init__(master)
                self.device = device
                self.title("Recuperar Código QR")
                self.geometry("400x200")
                self.resizable(False, False)
                self.transient(master)

                frame = ctk.CTkFrame(self)
                frame.pack(fill="both", expand=True, padx=20, pady=20)

                ctk.CTkLabel(
                    frame, text="Ingrese la contraseña para mostrar el código QR:",
                    font=ctk.CTkFont(size=12)
                ).pack(anchor="w", pady=(0, 10))

                self.pw = ctk.CTkEntry(frame, show="*")
                self.pw.pack(fill="x", pady=(0, 15))

                self.status = ctk.CTkLabel(frame, text="", font=ctk.CTkFont(size=11))
                self.status.pack()

                btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
                btn_frame.pack(fill="x")

                ctk.CTkButton(btn_frame, text="Cancelar", command=self.destroy).pack(side="left", padx=5)
                ctk.CTkButton(btn_frame, text="Mostrar QR", command=self._show).pack(side="right", padx=5)

            def _show(self):
                pw = self.pw.get()
                if not pw:
                    self.status.configure(text="Ingrese la contraseña", text_color="#f39c12")
                    return

                self.status.configure(text="🔍  Verificando...")
                t = threading.Thread(target=self._do_show, args=(pw,), daemon=True)
                t.start()

            def _do_show(self, pw):
                try:
                    secret = read_totp_secret(self.device, pw)
                    label = f"USB-Secure ({os.path.basename(self.device)})"
                    qr_img, uri = generate_qr_image(secret, label)

                    self.after(0, lambda: QRDialog(self, qr_img, secret, label, uri))
                    self.after(0, self.destroy)
                except USBCryptorError as e:
                    self.after(0, lambda: self.status.configure(
                        text=f"❌  {e}", text_color="#e74c3c"))
                except Exception as e:
                    self.after(0, lambda: self.status.configure(
                        text=f"❌  Error: {e}", text_color="#e74c3c"))

        RecoveryDialog(self, drive["device"])

    def _eject(self):
        drive = self.selected_drive
        if not drive:
            return
        self.status.configure(text="⏏  Expulsando...")

        def do_eject():
            try:
                lock_drive(drive["device"])
                self.after(0, lambda: self.status.configure(text="✅  Unidad expulsada"))
                self.after(0, self._refresh_drives)
            except USBCryptorError as e:
                self.after(0, lambda: self.status.configure(text=f"❌  {e}"))
            except Exception as e:
                self.after(0, lambda: self.status.configure(text=f"❌  Error: {e}"))

        t = threading.Thread(target=do_eject, daemon=True)
        t.start()
