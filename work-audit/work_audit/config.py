"""Configuración del módulo work-audit.

Usa un archivo TOML en la misma ubicación que la configuración de
ActivityWatch (%APPDATA%\\activitywatch\\work-audit\\work-audit.toml).
"""

import tomllib
from typing import Any, Dict

from . import paths

DEFAULT_CONFIG = """\
[work-audit]
# Usuario a registrar en el parte. Vacío => usuario de Windows.
usuario = ""

# Segundos entre sondeos de la ventana en primer plano.
poll_foreground = 1.0

# Segundos entre capturas periódicas mientras una app auditada sigue activa.
capture_interval = 30

# Hueco máximo (segundos) para fusionar segmentos consecutivos de la misma
# empresa en un único registro, evitando crear muchos registros pequeños.
merge_gap = 300

# Código de empresa por defecto para las aplicaciones no entrenables.
empresa_defecto = ""

# Segundos de inactividad (sin teclado/ratón) para cortar el segmento (AFK).
afk_timeout = 120

# Duración mínima (segundos); los segmentos más cortos se descartan.
min_segment = 5

# Aplicaciones que se registran como reuniones.
apps_reunion = ["ms-teams.exe", "teams.exe", "zoom.exe"]

# Origen del calendario: "outlook", "google" o "none".
calendar_source = "outlook"

# Ruta al credentials.json de Google (vacío => carpeta de configuración).
google_credentials = ""

# Actualizar la lista de empresas desde Biloop al iniciar la app.
empresas_autoupdate = false

# --- Acceso a Biloop ---
# URL base del portal Biloop, p.ej. https://auren.biloop.es
biloop_url = ""

# Subscription Key (UUID) del portal.
biloop_subscription_key = ""

# true => la key es de tipo USUARIO: no se envían USER/PASSWORD al portal.
biloop_key_tipo_usuario = false

# Último usuario de Biloop (solo se guarda si "recordar" está activo).
biloop_usuario = ""

# Recordar las credenciales de Biloop entre sesiones.
biloop_recordar = false

# Guardar un recorte de la región capturada para poder verificar imputaciones.
guardar_miniatura = true
"""


def _defaults() -> Dict[str, Any]:
    return tomllib.loads(DEFAULT_CONFIG)["work-audit"]


def load_config() -> Dict[str, Any]:
    """Carga la configuración, creando el archivo por defecto si no existe.

    Los valores del usuario se fusionan sobre los valores por defecto, de
    modo que claves nuevas en futuras versiones siempre tengan un valor.
    """
    cfg_file = paths.config_file()
    defaults = _defaults()

    if not cfg_file.exists():
        cfg_file.write_text(DEFAULT_CONFIG, encoding="utf-8")
        return defaults

    try:
        user = tomllib.loads(cfg_file.read_text(encoding="utf-8"))
        user_section = user.get("work-audit", {})
    except tomllib.TOMLDecodeError:
        # Config corrupta: usar valores por defecto sin sobreescribir el archivo.
        return defaults

    return {**defaults, **user_section}


_CONFIG_KEYS = [
    "usuario",
    "poll_foreground",
    "capture_interval",
    "merge_gap",
    "empresa_defecto",
    "afk_timeout",
    "min_segment",
    "apps_reunion",
    "calendar_source",
    "google_credentials",
    "empresas_autoupdate",
    "biloop_url",
    "biloop_subscription_key",
    "biloop_key_tipo_usuario",
    "biloop_usuario",
    "biloop_recordar",
    "guardar_miniatura",
]


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def save_config(cfg: Dict[str, Any]) -> None:
    """Guarda la configuración en work-audit.toml.

    Las claves de `cfg` se fusionan sobre la configuración actual, de modo
    que un guardado parcial (p. ej. desde una sola pestaña) no reinicia el
    resto de ajustes.
    """
    merged = {**load_config(), **cfg}
    defaults = _defaults()
    lines = ["[work-audit]"]
    for key in _CONFIG_KEYS:
        value = merged.get(key, defaults.get(key))
        lines.append(f"{key} = {_toml_value(value)}")
    paths.config_file().write_text("\n".join(lines) + "\n", encoding="utf-8")
