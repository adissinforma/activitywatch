"""Punto de entrada del módulo work-audit.

Arranca el servicio de auditoría en segundo plano, coloca el icono en la
bandeja del sistema y abre el Parte de Trabajo Diario.

Uso:
    python -m work_audit                Arranca todo y abre el parte diario.
    python -m work_audit --no-report    Arranca sin abrir el parte (solo bandeja).
"""

import argparse
import logging
import sys
import threading

from PyQt6 import QtWidgets

from .auditor import WorkAuditor
from .config import load_config
from .db import WorkAuditDB
from .seed import load_seed
from .ui.tray import WorkAuditTray


def _auto_update_empresas() -> None:
    """Sincroniza la lista de empresas desde Biloop si está activado.

    Se ejecuta en un hilo propio (con su propia conexión SQLite) para no
    bloquear el arranque de la interfaz.
    """
    log = logging.getLogger("work-audit")
    cfg = load_config()
    if not cfg.get("empresas_autoupdate"):
        return
    try:
        from .sync import sync_empresas_biloop

        db = WorkAuditDB()
        try:
            res = sync_empresas_biloop(db)
            log.info(
                "Empresas Biloop al iniciar · altas/actualizaciones=%s bajas=%s",
                res["upserted"],
                res["deleted"],
            )
        finally:
            db.close()
    except Exception as e:  # noqa: BLE001
        log.warning("No se pudieron actualizar las empresas: %s", e)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("work-audit")

    parser = argparse.ArgumentParser(description="Auditoría de trabajos")
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="No abrir el parte diario al arrancar",
    )
    args = parser.parse_args()

    # Inicializar la base de datos y cargar el seed de definiciones de captura.
    db = WorkAuditDB()
    cargadas = load_seed(db)
    if cargadas:
        log.info("Seed cargado: %d definiciones de captura", cargadas)

    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # la app vive en la bandeja

    if not QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
        log.warning("No hay bandeja del sistema disponible")

    # Servicio de auditoría en su propio hilo (con su propia conexión SQLite).
    auditor = WorkAuditor()
    auditor_thread = threading.Thread(
        target=auditor.run, name="work-auditor", daemon=True
    )
    auditor_thread.start()

    # Actualización de empresas desde el endpoint (en segundo plano).
    threading.Thread(
        target=_auto_update_empresas, name="empresas-sync", daemon=True
    ).start()

    tray = WorkAuditTray(db)
    tray.show()

    if not args.no_report:
        tray.show_report()

    exit_code = app.exec()

    # Cierre ordenado.
    log.info("Cerrando work-audit...")
    auditor.stop()
    auditor_thread.join(timeout=5)
    db.close()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
