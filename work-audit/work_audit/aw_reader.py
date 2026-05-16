"""Lectura de los tiempos de uso de aplicaciones desde ActivityWatch.

Consulta el servidor de ActivityWatch (localhost:5600) a través de la
librería aw-client y agrega la duración por aplicación.
"""

import logging
import socket
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


def _day_bounds(fecha: date):
    """Devuelve (inicio, fin) del día como datetimes con zona local."""
    start = datetime.combine(fecha, time()).astimezone()
    return start, start + timedelta(days=1)


def app_usage(
    fecha: Optional[date] = None, host: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Tiempo de uso por aplicación para un día.

    Args:
        fecha: día a consultar (por defecto, hoy).
        host: hostname del bucket (por defecto, el de esta máquina).

    Returns:
        Lista de {"app": str, "segundos": float} ordenada de mayor a menor.
        Lista vacía si el servidor de ActivityWatch no está disponible.
    """
    fecha = fecha or date.today()
    host = host or socket.gethostname()
    start, end = _day_bounds(fecha)

    try:
        import aw_client
    except ImportError:
        log.warning("aw-client no está instalado; no se puede leer ActivityWatch")
        return []

    bucket_id = f"aw-watcher-window_{host}"
    try:
        with aw_client.ActivityWatchClient("work-audit") as client:
            events = client.get_events(bucket_id, start=start, end=end)
    except Exception as e:  # noqa: BLE001
        log.warning("No se pudo consultar ActivityWatch (%s)", e)
        return []

    totales: Dict[str, float] = {}
    for ev in events:
        app = (ev.data or {}).get("app", "desconocido")
        totales[app] = totales.get(app, 0.0) + ev.duration.total_seconds()

    return sorted(
        ({"app": app, "segundos": seg} for app, seg in totales.items()),
        key=lambda r: r["segundos"],
        reverse=True,
    )
