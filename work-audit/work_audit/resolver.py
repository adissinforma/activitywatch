"""Resolución de la empresa a partir del texto OCR de las regiones.

Cada región capturada tiene un TIPO que indica qué representa su texto:
  - codempresa     : el texto es directamente el código de empresa.
  - nomempresa     : el texto es el nombre de la empresa.
  - codigorelacion : el texto es un identificador que, vía EMPRESAS_APLICACION,
                     se traduce a una empresa.
"""

import logging
import re
from typing import Any, Dict, List, Optional

from .db import WorkAuditDB

log = logging.getLogger(__name__)


def _clean(text: str, regex: Optional[str]) -> str:
    """Limpia el texto OCR; si hay regex, devuelve la primera coincidencia."""
    text = (text or "").strip()
    if regex:
        try:
            m = re.search(regex, text)
            if m:
                return m.group(0)
        except re.error as e:
            log.warning("Regex inválida '%s': %s", regex, e)
    return text


def resolve_empresa(
    db: WorkAuditDB, aplicacion: str, capturas_ocr: List[Dict[str, Any]]
) -> Dict[str, Optional[str]]:
    """Resuelve la empresa a partir de las regiones capturadas.

    Args:
        db: base de datos work-audit.
        aplicacion: nombre del proceso auditado.
        capturas_ocr: lista de dicts con claves:
            - "captura": fila de APLICACIONES_CAPTURAS (dict).
            - "texto": texto OCR crudo de esa región.

    Returns:
        dict con "codempresa", "nomempresa" e "informacion" (texto justificativo).
    """
    codempresa: Optional[str] = None
    nomempresa: Optional[str] = None
    partes_info: List[str] = []

    for item in capturas_ocr:
        cap = item["captura"]
        texto = _clean(item.get("texto", ""), cap.get("REGEX"))
        if not texto:
            continue
        partes_info.append(f"{cap['NOMBRE_CAMPO']}={texto}")

        tipo = (cap.get("TIPO") or "").lower()
        if tipo == "codempresa":
            codempresa = codempresa or texto
        elif tipo == "nomempresa":
            nomempresa = nomempresa or texto
        elif tipo == "codigorelacion":
            rel = db.find_relacion(aplicacion, texto)
            if rel:
                codempresa = codempresa or rel.get("CODEMPRESA")
                nomempresa = nomempresa or rel.get("NOMEMPRESA")

    # Completar el nombre desde la tabla EMPRESAS si tenemos el código.
    if codempresa and not nomempresa:
        emp = db.get_empresa(codempresa)
        if emp:
            nomempresa = emp.get("NOMEMPRESA")

    return {
        "codempresa": codempresa,
        "nomempresa": nomempresa,
        "informacion": " | ".join(partes_info),
    }


def default_company(
    db: WorkAuditDB, aplicacion: str, config: Dict[str, Any]
) -> Optional[str]:
    """Empresa por defecto de una aplicación no auditada.

    Usa la empresa configurada para esa app concreta
    (`APLICACIONES.CODEMPRESA_DEFECTO`) y, si no hay, la empresa por defecto
    global de la configuración.
    """
    row = db.get_aplicacion(aplicacion)
    if row and row.get("CODEMPRESA_DEFECTO"):
        return row["CODEMPRESA_DEFECTO"]
    return (config.get("empresa_defecto") or "").strip() or None
