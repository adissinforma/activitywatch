"""Almacenamiento seguro de contraseñas en el Almacén de credenciales de Windows.

La contraseña de Biloop nunca se guarda en el TOML. Se guarda mediante la API
de credenciales de Windows (`win32cred`), cifrada por el perfil del usuario.
Todas las credenciales del módulo comparten el destino ``work-audit:biloop``.
"""

import logging
from typing import Optional

log = logging.getLogger(__name__)

_TARGET = "work-audit:biloop"

try:
    import win32cred

    _DISPONIBLE = True
except ImportError:  # plataforma no Windows o pywin32 ausente
    _DISPONIBLE = False


def guardar_password(usuario: str, password: str) -> bool:
    """Guarda la contraseña de `usuario` en el almacén de credenciales.

    Devuelve True si se guardó correctamente.
    """
    if not _DISPONIBLE:
        log.warning("win32cred no disponible; la contraseña no se guarda")
        return False
    try:
        win32cred.CredWrite(
            {
                "Type": win32cred.CRED_TYPE_GENERIC,
                "TargetName": _TARGET,
                "UserName": usuario or "",
                "CredentialBlob": password or "",
                "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE,
            },
            0,
        )
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("No se pudo guardar la contraseña: %s", e)
        return False


def leer_password(usuario: str) -> Optional[str]:
    """Devuelve la contraseña guardada para `usuario`, o None si no hay.

    Solo la devuelve si el usuario almacenado coincide con el solicitado.
    """
    if not _DISPONIBLE:
        return None
    try:
        cred = win32cred.CredRead(_TARGET, win32cred.CRED_TYPE_GENERIC, 0)
    except Exception:  # noqa: BLE001  (no existe la credencial)
        return None
    if not cred:
        return None
    if (cred.get("UserName") or "").lower() != (usuario or "").lower():
        return None

    blob = cred.get("CredentialBlob")
    if blob is None:
        return None
    if isinstance(blob, bytes):
        for enc in ("utf-16-le", "utf-8"):
            try:
                return blob.decode(enc)
            except UnicodeDecodeError:
                continue
        return None
    return str(blob)


def olvidar_password(usuario: str) -> None:
    """Elimina la contraseña guardada. Silencioso si no existe."""
    if not _DISPONIBLE:
        return
    try:
        win32cred.CredDelete(_TARGET, win32cred.CRED_TYPE_GENERIC, 0)
    except Exception:  # noqa: BLE001  (no existía: nada que hacer)
        pass
