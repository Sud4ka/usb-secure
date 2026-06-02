# 🔐 USB Secure

Cifrado de pendrives con autenticación de dos factores (TOTP).

Cifra un pendrive completo con **LUKS** (Linux) o **VeraCrypt** (Windows) y agrega un segundo factor con Google Authenticator o similar. Sin el código 2FA no se puede montar la unidad, incluso teniendo la contraseña.

## Descargas

[![Release](https://img.shields.io/github/v/release/Sud4ka/usb-secure)](https://github.com/Sud4ka/usb-secure/releases/latest)

Bajá el ejecutable desde [GitHub Releases](https://github.com/Sud4ka/usb-secure/releases).

## Uso

### Linux

```bash
chmod +x USB_Secure
sudo -E ./USB_Secure
```

> `sudo -E` preserva las variables de entorno gráfico (`DISPLAY`, `XAUTHORITY`).  
> Si falla la conexión al servidor X, ejecutar antes: `xhost +SI:localuser:root`

**Requisitos:** `cryptsetup`, `mkfs.ext4`, `mount`, `umount`, `lsblk`  
`sudo apt install cryptsetup e2fsprogs mount util-linux`

Backend: **LUKS** (AES-256-XTS) + sistema de archivos **ext4**.

### Windows

```cmd
USB_Secure.exe
```

Ejecutar como **Administrador**.

**Requisitos:** [VeraCrypt](https://www.veracrypt.fr) instalado.

Backend: **VeraCrypt** (AES-256) + sistema de archivos **exFAT**.

## Cómo funciona

### ⚠️  ADVERTENCIA

> **Cifrar una unidad BORRA TODOS LOS ARCHIVOS existentes de forma permanente.**  
> No hay forma de recuperarlos después. Asegurate de tener un backup antes de continuar.

## Cifrar un pendrive

1. Conectá el pendrive → aparece en la lista
2. Seleccioná la unidad y presioná **Cifrar**
3. La app muestra una advertencia clara: todos los datos existentes serán borrados
4. Ingresá una contraseña (mínimo 8 caracteres)
5. La app:
   - Limpia el dispositivo (escribe ceros en los primeros sectores)
   - Crea el volumen cifrado (LUKS en Linux / VeraCrypt en Windows)
   - Genera un secreto TOTP y lo guarda dentro del volumen
   - Muestra un **código QR** para escanear con Google Authenticator
5. Escaneá el QR con tu celular → ya tenés el segundo factor

### Abrir una unidad cifrada

1. Seleccioná la unidad y presioná **Abrir**
2. Ingresá la **contraseña** y el **código 2FA** de la app autenticadora
3. La unidad se monta y podés leer/escribir archivos
4. Presioná **Expulsar** para desmontar y cerrar el cifrado

### Por qué es seguro

- La contraseña sola **no alcanza**: sin el código TOTP la unidad no se monta
- El secreto TOTP está almacenado **dentro del volumen cifrado**
- Al desbloquear, la app abre el volumen para leer el secreto, lo verifica, y solo si el código 2FA es correcto lo monta definitivamente
- Si el código es incorrecto, el volumen se cierra inmediatamente sin exponer datos

## Build desde código fuente

```bash
git clone https://github.com/Sud4ka/usb-secure.git
cd usb-secure
pip install -r requirements.txt pyinstaller
python build.py
```

El ejecutable se genera en `dist/`.

## Estructura del proyecto

```
usb-secure/
├── core/
│   ├── __init__.py    → Dispatcher: selecciona backend según plataforma
│   ├── common.py      → TOTP, QR, errores, utilidades
│   ├── linux.py       → Backend Linux: LUKS + cryptsetup
│   └── windows.py     → Backend Windows: VeraCrypt
├── main.py            → Entry point
├── ui.py              → GUI (customtkinter, dark mode)
├── build.py           → PyInstaller builder
└── .github/workflows/ → CI: build automático en Windows y Linux
```
