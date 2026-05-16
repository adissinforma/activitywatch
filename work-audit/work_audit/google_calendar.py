"""Lectura de Google Calendar mediante la API v3.

Requiere un cliente OAuth de escritorio: el usuario coloca su `credentials.json`
(generado gratis en Google Cloud Console) en la carpeta de configuración del
módulo o en la ruta indicada en la configuración. El token de acceso se cachea
para no repetir el consentimiento.
"""

import logging
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from . import paths
from .config import load_config
from .db import WorkAuditDB

log = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def _credentials_path() -> Path:
    ruta = load_config().get("google_credentials", "")
    if ruta:
        return Path(ruta)
    return paths.config_dir() / "credentials.json"


def _token_path() -> Path:
    return paths.data_dir() / "google_token.json"


def _get_service():
    """Construye el servicio de la API gestionando el OAuth. None si falla."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        log.info("Dependencias de Google no instaladas")
        return None

    creds = None
    token = _token_path()
    if token.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token), _SCOPES)
        except Exception as e:  # noqa: BLE001
            log.warning("Token de Google inválido: %s", e)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:  # noqa: BLE001
                log.warning("No se pudo refrescar el token de Google: %s", e)
                creds = None
        if not creds or not creds.valid:
            cred_file = _credentials_path()
            if not cred_file.exists():
                log.warning("Falta el credentials.json de Google: %s", cred_file)
                return None
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(cred_file), _SCOPES
                )
                creds = flow.run_local_server(port=0)
            except Exception as e:  # noqa: BLE001
                log.warning("Fallo en el consentimiento OAuth de Google: %s", e)
                return None
        try:
            token.write_text(creds.to_json(), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            log.warning("No se pudo guardar el token de Google: %s", e)

    try:
        return build("calendar", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:  # noqa: BLE001
        log.warning("No se pudo crear el servicio de Google Calendar: %s", e)
        return None


def _to_iso(campo: Optional[dict]) -> Optional[str]:
    """Convierte un campo start/end de Google a ISO local."""
    if not campo:
        return None
    raw = campo.get("dateTime") or campo.get("date")
    if not raw:
        return None
    try:
        if "T" not in raw:  # evento de todo el día (solo fecha)
            dt = datetime.fromisoformat(raw + "T00:00:00")
        else:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().isoformat()
    except ValueError:
        return None


def sync_calendar(db: WorkAuditDB, fecha, usuario: str) -> int:
    """Sincroniza los eventos del día desde Google Calendar.

    Returns:
        Número de eventos sincronizados, o -1 si Google no está disponible
        (sin credenciales o sin dependencias).
    """
    service = _get_service()
    if service is None:
        return -1

    try:
        inicio = datetime.combine(fecha, time()).astimezone()
        fin = inicio + timedelta(days=1)
        resultado = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=inicio.isoformat(),
                timeMax=fin.isoformat(),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        count = 0
        for ev in resultado.get("items", []):
            inicio_iso = _to_iso(ev.get("start"))
            if not inicio_iso:
                continue
            db.upsert_evento(
                usuario=usuario,
                inicio=inicio_iso,
                fin=_to_iso(ev.get("end")),
                asunto=ev.get("summary") or "",
                organizador=(ev.get("organizer") or {}).get("email", ""),
                id_externo="google:" + str(ev["id"]),
                origen="google",
            )
            count += 1
        log.info("Google Calendar: %d eventos sincronizados", count)
        return count
    except Exception as e:  # noqa: BLE001
        log.warning("No se pudo leer Google Calendar: %s", e)
        return -1
