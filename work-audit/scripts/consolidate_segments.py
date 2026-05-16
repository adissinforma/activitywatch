#!/usr/bin/env python3
"""Consolida registros antiguos de PARTE_TRABAJO.

Fusiona segmentos consecutivos del mismo usuario, aplicación y empresa
cuyo hueco no supere `merge_gap`, dejando un único registro por bloque de
trabajo. Pensado para ejecutarse una vez sobre datos anteriores a la
funcionalidad de fusión automática.

Uso:
    python scripts/consolidate_segments.py             Vista previa (no modifica).
    python scripts/consolidate_segments.py --apply     Aplica la consolidación.
    python scripts/consolidate_segments.py --gap 900   Hueco máximo en segundos.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from work_audit.config import load_config
from work_audit.db import WorkAuditDB


def _parse(ts):
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def _mismos(a, b):
    return (
        a["USUARIO"] == b["USUARIO"]
        and a["APLICACION"] == b["APLICACION"]
        and a["CODEMPRESA"] == b["CODEMPRESA"]
    )


def consolidar(db: WorkAuditDB, merge_gap: float, apply: bool) -> None:
    rows = db.conn.execute(
        "SELECT * FROM PARTE_TRABAJO WHERE HORAFIN IS NOT NULL "
        "ORDER BY USUARIO, APLICACION, HORAINICIO"
    ).fetchall()

    # Agrupar segmentos consecutivos fusionables.
    grupos = []
    actual = []
    for row in rows:
        if actual:
            prev = actual[-1]
            ini, fin = _parse(row["HORAINICIO"]), _parse(prev["HORAFIN"])
            hueco = (ini - fin).total_seconds() if ini and fin else None
            fusionable = (
                _mismos(row, prev)
                and hueco is not None
                and hueco <= merge_gap
            )
            if not fusionable:
                if len(actual) > 1:
                    grupos.append(actual)
                actual = []
        actual.append(row)
    if len(actual) > 1:
        grupos.append(actual)

    if not grupos:
        print("No hay registros que consolidar.")
        return

    eliminados = 0
    for grupo in grupos:
        primero, ultimo = grupo[0], grupo[-1]
        empresa = primero["CODEMPRESA"] or "(sin asignar)"
        print(
            f"  {primero['APLICACION']} · {empresa}: "
            f"{len(grupo)} registros -> 1  "
            f"({primero['HORAINICIO'][11:19]}–{ultimo['HORAFIN'][11:19]})"
        )
        if apply:
            # Conservar la primera información no vacía del grupo.
            info = next(
                (r["INFORMACION"] for r in grupo if r["INFORMACION"]),
                primero["INFORMACION"],
            )
            db.conn.execute(
                "UPDATE PARTE_TRABAJO SET HORAFIN = ?, INFORMACION = ? WHERE id = ?",
                (ultimo["HORAFIN"], info, primero["id"]),
            )
            for r in grupo[1:]:
                db.conn.execute("DELETE FROM PARTE_TRABAJO WHERE id = ?", (r["id"],))
                eliminados += 1

    if apply:
        db.conn.commit()
        print(f"\n✓ Consolidado: {len(grupos)} bloques, {eliminados} registros eliminados.")
    else:
        total = sum(len(g) - 1 for g in grupos)
        print(
            f"\nVista previa: {len(grupos)} bloques fusionables "
            f"({total} registros se eliminarían). Ejecuta con --apply para aplicar."
        )


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Consolida PARTE_TRABAJO")
    parser.add_argument("--apply", action="store_true", help="Aplicar los cambios")
    parser.add_argument(
        "--gap", type=float, default=None, help="Hueco máximo en segundos"
    )
    args = parser.parse_args()

    merge_gap = args.gap
    if merge_gap is None:
        merge_gap = float(load_config().get("merge_gap", 300))

    db = WorkAuditDB()
    db.conn.execute("PRAGMA busy_timeout = 5000")
    print(f"Base de datos: {db.path}")
    print(f"Hueco de fusión: {merge_gap:.0f} s\n")
    try:
        consolidar(db, merge_gap, apply=args.apply)
    finally:
        db.close()


if __name__ == "__main__":
    main()
