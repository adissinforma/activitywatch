#!/usr/bin/env python3
"""Genera un ejecutable independiente de work-audit con PyInstaller.

El .exe resultante NO necesita Python ni dependencias instaladas en el
equipo de destino: pensado para distribuir la aplicación.

Uso:
    pip install pyinstaller
    python scripts/build_exe.py             # carpeta dist/work-audit/
    python scripts/build_exe.py --onefile   # un único work-audit.exe

Resultado:
    --onedir (por defecto): dist/work-audit/work-audit.exe junto a sus
        dependencias. Arranca rápido; para distribuir se copia la carpeta
        entera.
    --onefile: dist/work-audit.exe, un solo archivo. Más cómodo de copiar,
        pero arranca más lento (se autoextrae en una carpeta temporal).

Varias dependencias (winsdk, aw_client, librerías de Google) se importan de
forma diferida, así que PyInstaller no las detecta solo: se recolectan aquí
de forma explícita con --collect-all.
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ROOT / "run_work_audit.py"


def main() -> None:
    parser = argparse.ArgumentParser(description="Compila work-audit.exe")
    parser.add_argument(
        "--onefile",
        action="store_true",
        help="Generar un único .exe en lugar de una carpeta",
    )
    args = parser.parse_args()

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("Falta PyInstaller. Instálalo con:  pip install pyinstaller")
        sys.exit(1)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",  # sin ventana de consola (la app vive en la bandeja)
        "--name",
        "work-audit",
        "--onefile" if args.onefile else "--onedir",
        # Dependencias con importación dinámica que PyInstaller no detecta:
        "--collect-all", "winsdk",                # OCR nativo de Windows
        "--collect-all", "aw_client",             # cliente de ActivityWatch
        "--collect-all", "googleapiclient",       # calendario de Google
        "--collect-all", "google",                # google.auth / google.oauth2
        "--collect-all", "google_auth_oauthlib",
        "--hidden-import", "win32timezone",       # usado por pywin32
        str(ENTRY),
    ]
    print("Ejecutando:\n  " + " ".join(cmd) + "\n")
    subprocess.run(cmd, cwd=str(ROOT), check=True)

    destino = (
        ROOT / "dist" / "work-audit.exe"
        if args.onefile
        else ROOT / "dist" / "work-audit" / "work-audit.exe"
    )
    print(f"\n✓ Ejecutable generado: {destino}")


if __name__ == "__main__":
    main()
