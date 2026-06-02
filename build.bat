@echo off
chcp 65001 >nul
title USB Secure - Build

echo ============================================
echo   USB Secure - Compilacion para Windows
echo ============================================
echo.

REM Check Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python no encontrado. Instale Python 3.13 desde python.org
    pause
    exit /b 1
)

REM Check PyInstaller
python -m pip show pyinstaller >nul 2>nul
if %errorlevel% neq 0 (
    echo [*] Instalando PyInstaller...
    python -m pip install pyinstaller
)

REM Install project dependencies
echo [*] Instalando dependencias...
python -m pip install -r requirements.txt

REM Build
echo [*] Compilando USB Secure...
python build.py

echo.
pause
