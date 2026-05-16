"""Lectura del calendario de Outlook de escritorio mediante automatización COM.

Sincroniza los eventos (citas) del día indicado en la tabla
EVENTOS_CALENDARIO. No requiere autenticación ni registro de aplicación:
usa el Outlook instalado en el equipo.
"""

import logging
from datetime import date, datetime, time, timedelta
from typing import Optional

from .db import WorkAuditDB

log = logging.getLogger(__name__)

_OL_FOLDER_CALENDAR = 9   # olFolderCalendar
_OL_CLASS_APPOINTMENT = 26  # olAppointment


def _to_iso(valor) -> str:
    """Convierte una fecha COM de Outlook (hora local) a ISO 8601."""
    try:
        dt = datetime(
            valor.year, valor.month, valor.day,
            valor.hour, valor.minute, valor.second,
        )
        return dt.astimezone().isoformat()
    except Exception:  # noqa: BLE001
        return str(valor)


def _organizador(item) -> str:
    try:
        return str(item.Organizer or "")
    except Exception:  # noqa: BLE001
        return ""


def sync_calendar(
    db: WorkAuditDB, fecha: date, usuario: str
) -> int:
    """Sincroniza los eventos del día desde Outlook a EVENTOS_CALENDARIO.

    Returns:
        Número de eventos sincronizados, o -1 si Outlook no está disponible.
    """
    try:
        import pythoncom
        import win32com.client
    except ImportError:
        log.info("pywin32 no disponible; se omite el calendario de Outlook")
        return -1

    coinit = False
    try:
        pythoncom.CoInitialize()
        coinit = True
    except Exception:  # noqa: BLE001
        pass

    try:
        namespace = win32com.client.Dispatch(
            "Outlook.Application"
        ).GetNamespace("MAPI")
        items = namespace.GetDefaultFolder(_OL_FOLDER_CALENDAR).Items
        items.IncludeRecurrences = True
        items.Sort("[Start]")

        inicio = datetime.combine(fecha, time())
        fin = inicio + timedelta(days=1)
        restriction = (
            f"[Start] >= '{inicio.strftime('%m/%d/%Y %H:%M')}' "
            f"AND [Start] < '{fin.strftime('%m/%d/%Y %H:%M')}'"
        )
        items = items.Restrict(restriction)

        count = 0
        for item in items:
            try:
                if getattr(item, "Class", _OL_CLASS_APPOINTMENT) != _OL_CLASS_APPOINTMENT:
                    continue
                db.upsert_evento(
                    usuario=usuario,
                    inicio=_to_iso(item.Start),
                    fin=_to_iso(item.End),
                    asunto=str(item.Subject or ""),
                    organizador=_organizador(item),
                    id_externo=str(item.EntryID),
                    origen="outlook",
                )
                count += 1
            except Exception as e:  # noqa: BLE001
                log.warning("Evento de Outlook omitido: %s", e)
        log.info("Calendario de Outlook: %d eventos sincronizados", count)
        return count
    except Exception as e:  # noqa: BLE001
        log.warning("No se pudo leer el calendario de Outlook: %s", e)
        return -1
    finally:
        if coinit:
            try:
                pythoncom.CoUninitialize()
            except Exception:  # noqa: BLE001
                pass
