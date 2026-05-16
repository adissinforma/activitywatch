"""Sincronización con sistemas externos.

Dos operaciones:
  1. Descargar el catálogo de empresas desde el portal Biloop.
  2. Subir los segmentos de PARTE_TRABAJO pendientes y marcarlos como
     sincronizados.

El catálogo de empresas se obtiene del portal Biloop (``biloop.py``): las
empresas autorizadas para las credenciales configuradas se vuelcan en la
tabla EMPRESAS. La subida de partes queda como punto de extensión marcado
con TODO hasta disponer de la especificación real del endpoint.
"""

import logging
import sys
from typing import Any, Dict, List

from .config import load_config
from .db import WorkAuditDB

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Descarga de EMPRESAS desde Biloop
# ---------------------------------------------------------------------------


def _empresa_de_biloop(c: Dict[str, Any]) -> Dict[str, Any]:
    """Convierte una empresa del modelo Biloop al modelo de la tabla EMPRESAS.

    Biloop entrega ``companyId``/``name``/``cif``/``program``; aquí se mapean
    a ``CODEMPRESA``/``NOMEMPRESA``/``CIF``/``PROGRAMA``.
    """
    return {
        "CODEMPRESA": str(c.get("companyId") or "").strip(),
        "NOMEMPRESA": str(c.get("name") or "").strip(),
        "CIF": str(c.get("cif") or "").strip(),
        "PROGRAMA": str(c.get("program") or "").strip(),
    }


def importar_empresas_biloop(
    db: WorkAuditDB, empresas_biloop: List[Dict[str, Any]]
) -> Dict[str, int]:
    """Sincroniza el catálogo EMPRESAS con una lista ya obtenida de Biloop.

    Da de alta/actualiza las empresas autorizadas y da de baja las que ya no
    lo están (solo las de origen Biloop; las manuales y de Excel se respetan).
    Pensada para usarse tras una comprobación de acceso interactiva, en la que
    la pestaña Empresas ya tiene la lista en mano.

    Si Biloop no devuelve ninguna empresa reconocible no se da nada de baja:
    una respuesta vacía suele indicar un problema puntual, no que el usuario
    haya perdido el acceso a todas sus empresas.

    Returns:
        ``{"upserted": altas+actualizaciones, "deleted": bajas}``.
    """
    empresas = [
        e
        for e in (_empresa_de_biloop(c) for c in empresas_biloop or [])
        if e["CODEMPRESA"]
    ]
    if not empresas:
        log.warning(
            "Biloop no devolvió empresas con código; no se sincroniza nada"
        )
        return {"upserted": 0, "deleted": 0}
    return db.sincronizar_empresas_biloop(empresas)


def sync_empresas_biloop(db: WorkAuditDB) -> Dict[str, int]:
    """Descarga las empresas autorizadas en Biloop y sincroniza EMPRESAS.

    Usa la configuración guardada (URL, subscription key, tipo de key y
    usuario) y, si la key es de tipo SISTEMA, la contraseña del Almacén de
    credenciales de Windows. Pensada para la actualización automática al
    iniciar la app: si falta configuración o no se recordó la contraseña,
    no sincroniza nada en lugar de fallar.

    Returns:
        ``{"upserted": altas+actualizaciones, "deleted": bajas}``.
    """
    cfg = load_config()
    url = str(cfg.get("biloop_url", "")).strip()
    key = str(cfg.get("biloop_subscription_key", "")).strip()
    if not url or not key:
        log.warning("Sincronización Biloop: falta URL o subscription key")
        return {"upserted": 0, "deleted": 0}

    from . import biloop
    from .credenciales import leer_password

    tipo_usuario = bool(cfg.get("biloop_key_tipo_usuario"))
    usuario = str(cfg.get("biloop_usuario", "")).strip()
    user = None if tipo_usuario else (usuario or None)
    password = None
    if not tipo_usuario and usuario:
        password = leer_password(usuario)

    cli = biloop.BiloopClient(url, key)
    token = cli.obtener_token(user, password)
    empresas = cli.listar_empresas(token)
    return importar_empresas_biloop(db, empresas)


# ---------------------------------------------------------------------------
# 2. Subida de PARTE_TRABAJO
# ---------------------------------------------------------------------------


def upload_partes(db: WorkAuditDB, endpoint: str) -> int:
    """Sube los segmentos de PARTE_TRABAJO pendientes y los marca como
    sincronizados.

    TODO: completar cuando se disponga del contrato del endpoint de subida
    (URL, método, autenticación y formato JSON esperado). De momento esta
    función prepara los datos y, si no hay endpoint, no hace nada.
    """
    pendientes = db.pendientes_sincronizar()
    if not pendientes:
        log.info("No hay partes pendientes de sincronizar")
        return 0

    if not endpoint:
        log.warning(
            "Hay %d partes pendientes pero no hay endpoint de subida configurado",
            len(pendientes),
        )
        return 0

    # --- Punto de extensión: ajustar al contrato real del endpoint --------
    # import requests
    # payload = [
    #     {
    #         "usuario": p["USUARIO"],
    #         "horainicio": p["HORAINICIO"],
    #         "horafin": p["HORAFIN"],
    #         "aplicacion": p["APLICACION"],
    #         "informacion": p["INFORMACION"],
    #         "codempresa": p["CODEMPRESA"],
    #     }
    #     for p in pendientes
    # ]
    # resp = requests.post(endpoint, json=payload, timeout=60)
    # resp.raise_for_status()
    # db.marcar_sincronizados([p["id"] for p in pendientes])
    # return len(pendientes)
    log.warning(
        "Subida de partes no implementada: falta el contrato del endpoint. "
        "%d segmentos preparados.",
        len(pendientes),
    )
    return 0


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    db = WorkAuditDB()
    try:
        res = sync_empresas_biloop(db)
        print(
            f"Empresas Biloop · altas/actualizaciones: {res['upserted']}, "
            f"bajas: {res['deleted']}"
        )
        subidos = upload_partes(db, "")
        print(f"Partes subidos: {subidos}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
