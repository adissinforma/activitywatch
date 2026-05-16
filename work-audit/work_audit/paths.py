"""Resolución de rutas del módulo work-audit.

Reutiliza la convención de carpetas de ActivityWatch en Windows para que
los datos del módulo queden junto a los de AW, pero en su propia subcarpeta.
"""

import os
from pathlib import Path

APP_DIRNAME = "work-audit"


def data_dir() -> Path:
    """Carpeta de datos (base de datos, miniaturas). Se crea si no existe."""
    local = os.environ.get("LOCALAPPDATA")
    if local:
        d = Path(local) / "activitywatch" / "activitywatch" / APP_DIRNAME
    else:
        d = Path.home() / ".local" / "share" / "activitywatch" / APP_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_dir() -> Path:
    """Carpeta de configuración (work-audit.toml). Se crea si no existe."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        d = Path(appdata) / "activitywatch" / APP_DIRNAME
    else:
        d = Path.home() / ".config" / "activitywatch" / APP_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    """Ruta del archivo SQLite work_audit.db."""
    return data_dir() / "work_audit.db"


def thumbnails_dir() -> Path:
    """Carpeta donde se guardan las miniaturas de las regiones capturadas."""
    d = data_dir() / "thumbnails"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_file() -> Path:
    """Ruta del archivo work-audit.toml."""
    return config_dir() / "work-audit.toml"


def seed_file() -> Path:
    """Ruta del seed de definiciones de capturas (entregado con la instalación)."""
    return Path(__file__).resolve().parent.parent / "seed" / "capturas.seed.json"
