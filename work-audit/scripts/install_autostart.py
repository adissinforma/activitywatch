#!/usr/bin/env python3
"""Registra (o elimina) el arranque automático de work-audit al iniciar sesión.

Crea un acceso directo en la carpeta de Inicio de Windows que lanza el
módulo con pythonw.exe (sin consola). Así, al encender el equipo, se abre
el Parte de Trabajo Diario.

Uso:
    python scripts/install_autostart.py            Instala el arranque.
    python scripts/install_autostart.py --remove   Lo elimina.
"""

import argparse
import os
import sys
from pathlib import Path

SHORTCUT_NAME = "work-audit.lnk"


def _startup_dir() -> Path:
    appdata = os.environ.get("APPDATA", "")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _pythonw() -> Path:
    """Ruta de pythonw.exe (intérprete sin ventana de consola)."""
    candidate = Path(sys.executable).with_name("pythonw.exe")
    return candidate if candidate.exists() else Path(sys.executable)


def _module_dir() -> Path:
    """Carpeta 'work-audit' que contiene el paquete work_audit."""
    return Path(__file__).resolve().parent.parent


def install() -> None:
    try:
        from win32com.client import Dispatch
    except ImportError:
        print("ERROR: se requiere pywin32 (pip install pywin32).")
        sys.exit(1)

    shortcut_path = _startup_dir() / SHORTCUT_NAME
    shell = Dispatch("WScript.Shell")
    shortcut = shell.CreateShortcut(str(shortcut_path))
    shortcut.TargetPath = str(_pythonw())
    shortcut.Arguments = "-m work_audit"
    shortcut.WorkingDirectory = str(_module_dir())
    shortcut.Description = "work-audit · Auditoría de trabajos"
    shortcut.Save()
    print(f"✓ Arranque automático instalado: {shortcut_path}")


def remove() -> None:
    shortcut_path = _startup_dir() / SHORTCUT_NAME
    if shortcut_path.exists():
        shortcut_path.unlink()
        print(f"✓ Arranque automático eliminado: {shortcut_path}")
    else:
        print("No había arranque automático instalado.")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Arranque automático de work-audit")
    parser.add_argument("--remove", action="store_true", help="Eliminar el arranque")
    args = parser.parse_args()
    remove() if args.remove else install()


if __name__ == "__main__":
    main()
