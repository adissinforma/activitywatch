"""Servicio de auditoría en segundo plano.

Sondea la ventana en primer plano y registra TODA la actividad en
PARTE_TRABAJO, asociando cada periodo de trabajo a una empresa cliente:

  - Apps auditadas (con regiones de captura): empresa resuelta por OCR; si no
    se resuelve, se deja en blanco para que el usuario la rellene.
  - Apps no auditadas: empresa por defecto (override por app o global).

El tiempo de inactividad (AFK) no se registra: si el usuario se ausenta, el
segmento se cierra retrodatándolo al inicio de la inactividad y no se fusiona
con la actividad posterior.

Un segmento se identifica por (aplicación, empresa, tipo): mientras no cambie
ninguno de los tres, sigue abierto.
"""

import logging
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from . import paths
from .capture import capture_region
from .config import load_config
from .db import WorkAuditDB, default_user
from .foreground import WindowInfo, get_foreground_window
from .idle import idle_seconds
from .ocr import is_available as ocr_available
from .ocr import ocr_image
from .resolver import default_company, resolve_empresa

log = logging.getLogger(__name__)


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return None


class WorkAuditor:
    """Bucle de auditoría. Pensado para ejecutarse en su propio hilo."""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        db_path: Optional[str] = None,
    ):
        # La conexión SQLite se abre en run(), dentro del hilo del auditor.
        self.db_path = db_path
        self.db: Optional[WorkAuditDB] = None

        cfg = config or load_config()
        self.cfg = cfg
        self.usuario: str = cfg.get("usuario") or default_user()
        self.poll: float = float(cfg.get("poll_foreground", 1.0))
        self.capture_interval: float = float(cfg.get("capture_interval", 30))
        self.merge_gap: float = float(cfg.get("merge_gap", 300))
        self.afk_timeout: float = float(cfg.get("afk_timeout", 120))
        self.min_segment: float = float(cfg.get("min_segment", 5))
        self.guardar_miniatura: bool = bool(cfg.get("guardar_miniatura", True))
        self.apps_reunion = {
            str(a).lower() for a in cfg.get("apps_reunion", [])
        }

        self._stop = threading.Event()
        self._last_capture = 0.0
        # Segmento abierto actual: {segment_id, app, codempresa, tipo}
        self._current: Optional[Dict[str, Any]] = None
        self._afk = False
        # Tras una pausa AFK no se fusiona con el segmento anterior.
        self._block_merge = False

    # -- control ------------------------------------------------------------

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        """Bucle principal. Bloquea hasta que se llame a stop()."""
        self.db = WorkAuditDB(self.db_path)
        try:
            if not ocr_available():
                log.warning(
                    "El OCR nativo de Windows no está disponible; "
                    "las apps auditadas se registrarán sin empresa."
                )
            stale = self.db.get_open_segment(self.usuario)
            if stale:
                self.db.close_segment(stale["id"])
                log.info("Cerrado segmento huérfano #%s", stale["id"])

            log.info("Auditor iniciado (usuario=%s)", self.usuario)
            while not self._stop.is_set():
                try:
                    self._tick()
                except Exception as e:  # noqa: BLE001
                    log.warning("Error en el ciclo de auditoría: %s", e)
                self._stop.wait(self.poll)

            self._close_current()
            log.info("Auditor detenido")
        finally:
            self.db.close()
            self.db = None

    # -- ciclo --------------------------------------------------------------

    def _tick(self) -> None:
        # 1. Inactividad (AFK): cerrar el segmento retrodatándolo.
        idle = idle_seconds()
        if idle >= self.afk_timeout:
            if self._current is not None:
                fin = datetime.now(timezone.utc) - timedelta(seconds=idle)
                self._close_current(horafin=fin.isoformat())
                self._block_merge = True
            self._afk = True
            return
        self._afk = False

        # 2. Ventana en primer plano.
        win = get_foreground_window()
        if win is None or not win.app:
            self._close_current()
            self._last_capture = 0.0
            return

        app = win.app
        tipo = "reunion" if app in self.apps_reunion else "app"

        # 3. ¿Toca re-inspeccionar?
        now = time.monotonic()
        focus_changed = self._current is None or self._current["app"] != app
        due = (now - self._last_capture) >= self.capture_interval
        if not (focus_changed or due):
            return
        self._last_capture = now

        # 4. Resolver la empresa.
        if self._is_audited(app):
            resolved, results = self._inspect(win)
            company = resolved.get("codempresa")
            info = resolved.get("informacion")
        else:
            company = default_company(self.db, app, self.cfg)
            info = None
            results = []

        self._apply(app, company, info, tipo, results)

    def _is_audited(self, app: str) -> bool:
        """Una app es auditable si está activa y tiene regiones de captura."""
        row = self.db.get_aplicacion(app)
        if not row or not row["activo"]:
            return False
        return len(self.db.get_capturas(app)) > 0

    def _inspect(self, win: WindowInfo):
        """Captura y OCR de todas las regiones definidas para la app."""
        capturas = self.db.get_capturas(win.app)
        results: List[Dict[str, Any]] = []
        for cap in capturas:
            texto = ""
            img = None
            try:
                img = capture_region(
                    win.client_rect,
                    (cap["X"], cap["Y"], cap["ANCHO"], cap["ALTO"]),
                    (cap["REF_ANCHO"], cap["REF_ALTO"]),
                )
                texto = ocr_image(img)
            except Exception as e:  # noqa: BLE001
                log.warning("Fallo capturando región '%s': %s", cap["NOMBRE_CAMPO"], e)
            results.append({"captura": cap, "texto": texto, "img": img})

        resolved = resolve_empresa(self.db, win.app, results)
        return resolved, results

    def _apply(
        self,
        app: str,
        company: Optional[str],
        info: Optional[str],
        tipo: str,
        results: List[Dict[str, Any]],
    ) -> None:
        """Abre/cierra segmentos según el resultado de la inspección."""
        cur = self._current
        if (
            cur
            and cur["app"] == app
            and cur["codempresa"] == company
            and cur["tipo"] == tipo
        ):
            return  # mismo trabajo: el segmento sigue abierto

        self._close_current()
        seg_id, reanudado = self._resume_or_open(app, company, info, tipo)
        self._current = {
            "segment_id": seg_id,
            "app": app,
            "codempresa": company,
            "tipo": tipo,
        }
        log.info(
            "%s segmento #%s: app=%s empresa=%s tipo=%s",
            "Reanudado" if reanudado else "Nuevo",
            seg_id, app, company or "?", tipo,
        )
        if not reanudado and self.guardar_miniatura:
            self._save_thumbnails(seg_id, results)

    def _resume_or_open(
        self, app: str, company: Optional[str], info: Optional[str], tipo: str
    ) -> Tuple[int, bool]:
        """Reanuda el último segmento si coincide app/empresa/tipo y el hueco
        es corto; en caso contrario abre uno nuevo. Devuelve (id, reanudado)."""
        if not self._block_merge:
            prev = self.db.last_closed_segment(self.usuario)
            if (
                prev
                and prev["APLICACION"] == app
                and prev["CODEMPRESA"] == company
                and prev["TIPO"] == tipo
            ):
                fin = _parse_iso(prev["HORAFIN"])
                if fin:
                    hueco = (datetime.now(timezone.utc) - fin).total_seconds()
                    if hueco <= self.merge_gap:
                        self.db.reopen_segment(prev["id"])
                        return prev["id"], True

        self._block_merge = False
        seg_id = self.db.open_segment(
            self.usuario, app, company, info, tipo=tipo
        )
        return seg_id, False

    def _close_current(self, horafin: Optional[str] = None) -> None:
        """Cierra el segmento abierto; lo descarta si es más corto que
        `min_segment`."""
        if not self._current:
            return
        seg_id = self._current["segment_id"]

        # Al retrodatar por AFK, evitar un HORAFIN anterior al HORAINICIO.
        if horafin:
            previo = self.db.get_segment(seg_id)
            ini = _parse_iso(previo["HORAINICIO"]) if previo else None
            fin = _parse_iso(horafin)
            if ini and fin and fin < ini:
                horafin = previo["HORAINICIO"]
        self.db.close_segment(seg_id, horafin)

        seg = self.db.get_segment(seg_id)
        if seg:
            ini = _parse_iso(seg["HORAINICIO"])
            fin = _parse_iso(seg["HORAFIN"])
            if ini and fin and (fin - ini).total_seconds() < self.min_segment:
                self.db.delete_segment(seg_id)
                log.info("Segmento #%s descartado (< %.0f s)", seg_id, self.min_segment)
            else:
                log.info("Segmento #%s cerrado", seg_id)
        self._current = None

    def _save_thumbnails(
        self, segment_id: int, results: List[Dict[str, Any]]
    ) -> None:
        """Guarda un recorte de cada región para poder verificar la imputación."""
        for item in results:
            img = item.get("img")
            if img is None:
                continue
            campo = item["captura"]["NOMBRE_CAMPO"]
            try:
                dest = paths.thumbnails_dir() / f"seg{segment_id}_{campo}.png"
                img.save(dest)
            except Exception as e:  # noqa: BLE001
                log.warning("No se pudo guardar miniatura: %s", e)


def main() -> None:
    """Ejecuta el auditor en primer plano (Ctrl+C para detener)."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    auditor = WorkAuditor()
    thread = threading.Thread(target=auditor.run, name="work-auditor")
    thread.start()
    try:
        while thread.is_alive():
            thread.join(timeout=0.5)
    except KeyboardInterrupt:
        print("\nDeteniendo auditor...")
        auditor.stop()
        thread.join()


if __name__ == "__main__":
    main()
