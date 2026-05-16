"""Carga del seed de definiciones de capturas (APLICACIONES_CAPTURAS).

Las definiciones de regiones son comunes a todos los usuarios y se entregan
con la instalación en seed/capturas.seed.json. La carga es idempotente: se
puede ejecutar en cada arranque sin duplicar datos.
"""

import json
from pathlib import Path
from typing import Optional

from . import paths
from .db import WorkAuditDB


def load_seed(db: WorkAuditDB, seed_path: Optional[Path] = None) -> int:
    """Carga el seed en la base de datos. Devuelve el nº de capturas cargadas.

    Las claves que empiezan por "_" (documentación/ejemplos) se ignoran.
    """
    seed_path = seed_path or paths.seed_file()
    if not seed_path.exists():
        return 0

    data = json.loads(seed_path.read_text(encoding="utf-8"))
    capturas_cargadas = 0

    for app in data.get("aplicaciones", []):
        aplicacion = app.get("aplicacion")
        if not aplicacion:
            continue
        db.upsert_aplicacion(aplicacion, app.get("ruta", ""))
        for cap in app.get("capturas", []):
            db.upsert_captura(
                aplicacion=aplicacion,
                nombre_campo=cap["nombre_campo"],
                tipo=cap["tipo"],
                x=int(cap["x"]),
                y=int(cap["y"]),
                ancho=int(cap["ancho"]),
                alto=int(cap["alto"]),
                ref_ancho=int(cap["ref_ancho"]),
                ref_alto=int(cap["ref_alto"]),
                regex=cap.get("regex"),
            )
            capturas_cargadas += 1

    return capturas_cargadas


def export_seed(db: WorkAuditDB, seed_path: Optional[Path] = None) -> Path:
    """Exporta las APLICACIONES y sus capturas actuales al archivo seed.

    Lo usa la herramienta de marcado para persistir definiciones nuevas y
    poder distribuirlas a otras instalaciones.
    """
    seed_path = seed_path or paths.seed_file()
    aplicaciones = []
    for app in db.list_aplicaciones():
        capturas = [
            {
                "nombre_campo": c["NOMBRE_CAMPO"],
                "tipo": c["TIPO"],
                "x": c["X"],
                "y": c["Y"],
                "ancho": c["ANCHO"],
                "alto": c["ALTO"],
                "ref_ancho": c["REF_ANCHO"],
                "ref_alto": c["REF_ALTO"],
                "regex": c["REGEX"],
            }
            for c in db.get_capturas(app["APLICACION"])
        ]
        aplicaciones.append(
            {
                "aplicacion": app["APLICACION"],
                "ruta": app["RUTA"] or "",
                "capturas": capturas,
            }
        )

    payload = {
        "_descripcion": "Definiciones de regiones de captura por aplicación.",
        "aplicaciones": aplicaciones,
    }
    seed_path.parent.mkdir(parents=True, exist_ok=True)
    seed_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return seed_path
