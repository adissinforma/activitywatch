#!/usr/bin/env python3
"""Capa de base de datos del módulo de Auditoría de Trabajos.

Gestiona work_audit.db (SQLite), un archivo independiente de la base de
datos de ActivityWatch. Contiene las tablas EMPRESAS, EMPRESAS_APLICACION,
APLICACIONES, APLICACIONES_CAPTURAS y PARTE_TRABAJO.

Uso por línea de comandos:
    python -m work_audit.db --init      Crea/actualiza el esquema.
    python -m work_audit.db --info      Muestra ruta y conteos de tablas.
"""

import argparse
import getpass
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import paths

# ---------------------------------------------------------------------------
# Esquema
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS EMPRESAS (
    CODEMPRESA   TEXT PRIMARY KEY,
    NOMEMPRESA   TEXT,
    CIF          TEXT,
    PROGRAMA     TEXT,
    ORIGEN       TEXT,
    actualizado  TEXT
);

CREATE TABLE IF NOT EXISTS EMPRESAS_APLICACION (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    APLICACION           TEXT NOT NULL,
    CODEMPRESA           TEXT,
    NOMEMPRESA           TEXT,
    CODIGORELACION       TEXT,
    DESCRIPCIONRELACION  TEXT,
    UNIQUE (APLICACION, CODIGORELACION)
);

CREATE TABLE IF NOT EXISTS APLICACIONES (
    APLICACION          TEXT PRIMARY KEY,
    RUTA                TEXT,
    activo              INTEGER NOT NULL DEFAULT 1,
    CODEMPRESA_DEFECTO  TEXT
);

CREATE TABLE IF NOT EXISTS APLICACIONES_CAPTURAS (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    APLICACION    TEXT NOT NULL,
    NOMBRE_CAMPO  TEXT NOT NULL,
    TIPO          TEXT NOT NULL,
    X             INTEGER NOT NULL,
    Y             INTEGER NOT NULL,
    ANCHO         INTEGER NOT NULL,
    ALTO          INTEGER NOT NULL,
    REF_ANCHO     INTEGER NOT NULL,
    REF_ALTO      INTEGER NOT NULL,
    REGEX         TEXT,
    UNIQUE (APLICACION, NOMBRE_CAMPO)
);

CREATE TABLE IF NOT EXISTS PARTE_TRABAJO (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    USUARIO       TEXT NOT NULL,
    HORAINICIO    TEXT NOT NULL,
    HORAFIN       TEXT,
    APLICACION    TEXT NOT NULL,
    INFORMACION   TEXT,
    CODEMPRESA    TEXT,
    TIPO          TEXT NOT NULL DEFAULT 'app',
    SINCRONIZADO  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS EVENTOS_CALENDARIO (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    USUARIO       TEXT NOT NULL,
    INICIO        TEXT NOT NULL,
    FIN           TEXT,
    ASUNTO        TEXT,
    ORGANIZADOR   TEXT,
    CODEMPRESA    TEXT,
    ORIGEN        TEXT,
    PARTE_ID      INTEGER,
    ID_EXTERNO    TEXT UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_parte_inicio ON PARTE_TRABAJO (HORAINICIO);
CREATE INDEX IF NOT EXISTS idx_capturas_app ON APLICACIONES_CAPTURAS (APLICACION);
CREATE INDEX IF NOT EXISTS idx_emprel_app   ON EMPRESAS_APLICACION (APLICACION);
CREATE INDEX IF NOT EXISTS idx_evento_inicio ON EVENTOS_CALENDARIO (INICIO);
"""

TABLES = [
    "EMPRESAS",
    "EMPRESAS_APLICACION",
    "APLICACIONES",
    "APLICACIONES_CAPTURAS",
    "PARTE_TRABAJO",
    "EVENTOS_CALENDARIO",
]


def now_iso() -> str:
    """Marca de tiempo actual en UTC, formato ISO 8601."""
    return datetime.now(timezone.utc).isoformat()


def default_user() -> str:
    """Usuario de Windows actual."""
    try:
        return getpass.getuser()
    except Exception:
        return "desconocido"


# ---------------------------------------------------------------------------
# Capa de acceso
# ---------------------------------------------------------------------------


class WorkAuditDB:
    """Acceso a work_audit.db. Crea el esquema automáticamente al conectar."""

    def __init__(self, path: Optional[str] = None):
        self.path = Path(path) if path else paths.db_path()
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        # WAL permite que el parte diario lea mientras el auditor escribe.
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.init_schema()

    def init_schema(self) -> None:
        """Crea las tablas e índices si no existen y migra esquemas antiguos."""
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self._migrate()

    def _migrate(self) -> None:
        """Añade columnas nuevas a bases de datos creadas con esquemas previos."""

        def columnas(tabla: str) -> set:
            return {
                row[1] for row in self.conn.execute(f"PRAGMA table_info({tabla})")
            }

        if "CODEMPRESA_DEFECTO" not in columnas("APLICACIONES"):
            self.conn.execute(
                "ALTER TABLE APLICACIONES ADD COLUMN CODEMPRESA_DEFECTO TEXT"
            )
        if "CIF" not in columnas("EMPRESAS"):
            self.conn.execute("ALTER TABLE EMPRESAS ADD COLUMN CIF TEXT")
        if "ORIGEN" not in columnas("EMPRESAS"):
            # Empresas previas quedan con ORIGEN nulo: nunca son de Biloop y,
            # por tanto, la baja automática no las toca.
            self.conn.execute("ALTER TABLE EMPRESAS ADD COLUMN ORIGEN TEXT")
        if "PROGRAMA" not in columnas("EMPRESAS"):
            self.conn.execute("ALTER TABLE EMPRESAS ADD COLUMN PROGRAMA TEXT")
        if "TIPO" not in columnas("PARTE_TRABAJO"):
            self.conn.execute(
                "ALTER TABLE PARTE_TRABAJO "
                "ADD COLUMN TIPO TEXT NOT NULL DEFAULT 'app'"
            )

        ev_cols = columnas("EVENTOS_CALENDARIO")
        if "OUTLOOK_ID" in ev_cols and "ID_EXTERNO" not in ev_cols:
            self.conn.execute(
                "ALTER TABLE EVENTOS_CALENDARIO "
                "RENAME COLUMN OUTLOOK_ID TO ID_EXTERNO"
            )
            ev_cols = columnas("EVENTOS_CALENDARIO")
        if "ORIGEN" not in ev_cols:
            self.conn.execute(
                "ALTER TABLE EVENTOS_CALENDARIO ADD COLUMN ORIGEN TEXT"
            )
        if "PARTE_ID" not in ev_cols:
            self.conn.execute(
                "ALTER TABLE EVENTOS_CALENDARIO ADD COLUMN PARTE_ID INTEGER"
            )
        self.conn.commit()

    # -- EMPRESAS -----------------------------------------------------------

    def upsert_empresas(
        self, empresas: List[Dict[str, Any]], origen: str = "manual"
    ) -> int:
        """Inserta o actualiza empresas. Cada dict: {CODEMPRESA, NOMEMPRESA,
        CIF, PROGRAMA}.

        ``origen`` ('manual' | 'excel' | 'biloop') solo se registra al dar de
        alta una empresa nueva; al actualizar una ya existente no se modifica,
        de modo que una empresa nunca cambia de origen por sí sola.
        """
        ts = now_iso()
        rows = [
            (
                e["CODEMPRESA"],
                e.get("NOMEMPRESA"),
                e.get("CIF"),
                e.get("PROGRAMA"),
                ts,
                origen,
            )
            for e in empresas
        ]
        self.conn.executemany(
            "INSERT INTO EMPRESAS "
            "(CODEMPRESA, NOMEMPRESA, CIF, PROGRAMA, actualizado, ORIGEN) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(CODEMPRESA) DO UPDATE SET "
            "NOMEMPRESA=excluded.NOMEMPRESA, CIF=excluded.CIF, "
            "PROGRAMA=excluded.PROGRAMA, actualizado=excluded.actualizado",
            rows,
        )
        self.conn.commit()
        return len(rows)

    def sincronizar_empresas_biloop(
        self, empresas: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """Sincroniza el catálogo con las empresas autorizadas en Biloop.

        Alta/actualización de las recibidas (las nuevas con ORIGEN='biloop') y
        baja de las que, teniendo ORIGEN='biloop', ya no figuran en la lista.
        Las empresas de origen manual o Excel no se tocan nunca.

        Returns:
            ``{"upserted": altas+actualizaciones, "deleted": bajas}``.
        """
        ts = now_iso()
        rows = [
            (
                e["CODEMPRESA"],
                e.get("NOMEMPRESA"),
                e.get("CIF"),
                e.get("PROGRAMA"),
                ts,
            )
            for e in empresas
            if e.get("CODEMPRESA")
        ]
        codigos = {r[0] for r in rows}

        self.conn.executemany(
            "INSERT INTO EMPRESAS "
            "(CODEMPRESA, NOMEMPRESA, CIF, PROGRAMA, actualizado, ORIGEN) "
            "VALUES (?, ?, ?, ?, ?, 'biloop') "
            "ON CONFLICT(CODEMPRESA) DO UPDATE SET "
            "NOMEMPRESA=excluded.NOMEMPRESA, CIF=excluded.CIF, "
            "PROGRAMA=excluded.PROGRAMA, actualizado=excluded.actualizado",
            rows,
        )

        biloop_actuales = {
            r[0]
            for r in self.conn.execute(
                "SELECT CODEMPRESA FROM EMPRESAS WHERE ORIGEN = 'biloop'"
            )
        }
        a_borrar = biloop_actuales - codigos
        if a_borrar:
            self.conn.executemany(
                "DELETE FROM EMPRESAS WHERE CODEMPRESA = ?",
                [(c,) for c in a_borrar],
            )
        self.conn.commit()
        return {"upserted": len(rows), "deleted": len(a_borrar)}

    def delete_empresa(self, codempresa: str) -> None:
        self.conn.execute(
            "DELETE FROM EMPRESAS WHERE CODEMPRESA = ?", (codempresa,)
        )
        self.conn.commit()

    def get_empresa(self, codempresa: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM EMPRESAS WHERE CODEMPRESA = ?", (codempresa,)
        ).fetchone()
        return dict(row) if row else None

    def all_empresas(self) -> List[Dict[str, Any]]:
        return [
            dict(r)
            for r in self.conn.execute(
                "SELECT * FROM EMPRESAS ORDER BY NOMEMPRESA"
            ).fetchall()
        ]

    # -- EMPRESAS_APLICACION -----------------------------------------------

    def upsert_relacion(
        self,
        aplicacion: str,
        codigorelacion: str,
        codempresa: Optional[str] = None,
        nomempresa: Optional[str] = None,
        descripcionrelacion: Optional[str] = None,
    ) -> None:
        """Registra/actualiza una relación que vincula un código detectado
        por OCR con una empresa, para una aplicación concreta."""
        self.conn.execute(
            "INSERT INTO EMPRESAS_APLICACION "
            "(APLICACION, CODEMPRESA, NOMEMPRESA, CODIGORELACION, DESCRIPCIONRELACION) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(APLICACION, CODIGORELACION) DO UPDATE SET "
            "CODEMPRESA=excluded.CODEMPRESA, NOMEMPRESA=excluded.NOMEMPRESA, "
            "DESCRIPCIONRELACION=excluded.DESCRIPCIONRELACION",
            (aplicacion, codempresa, nomempresa, codigorelacion, descripcionrelacion),
        )
        self.conn.commit()

    def find_relacion(
        self, aplicacion: str, codigorelacion: str
    ) -> Optional[Dict[str, Any]]:
        """Busca la empresa asociada a un código de relación exacto."""
        row = self.conn.execute(
            "SELECT * FROM EMPRESAS_APLICACION "
            "WHERE APLICACION = ? AND CODIGORELACION = ?",
            (aplicacion, codigorelacion),
        ).fetchone()
        return dict(row) if row else None

    def relaciones_de(self, aplicacion: str) -> List[Dict[str, Any]]:
        return [
            dict(r)
            for r in self.conn.execute(
                "SELECT * FROM EMPRESAS_APLICACION WHERE APLICACION = ?",
                (aplicacion,),
            ).fetchall()
        ]

    # -- APLICACIONES -------------------------------------------------------

    def upsert_aplicacion(
        self, aplicacion: str, ruta: str = "", activo: bool = True
    ) -> None:
        self.conn.execute(
            "INSERT INTO APLICACIONES (APLICACION, RUTA, activo) VALUES (?, ?, ?) "
            "ON CONFLICT(APLICACION) DO UPDATE SET RUTA=excluded.RUTA",
            (aplicacion, ruta, 1 if activo else 0),
        )
        self.conn.commit()

    def set_aplicacion_activo(self, aplicacion: str, activo: bool) -> None:
        self.conn.execute(
            "UPDATE APLICACIONES SET activo = ? WHERE APLICACION = ?",
            (1 if activo else 0, aplicacion),
        )
        self.conn.commit()

    def set_aplicacion_empresa_defecto(
        self, aplicacion: str, codempresa: Optional[str]
    ) -> None:
        """Fija la empresa por defecto de una aplicación (override por app)."""
        self.conn.execute(
            "UPDATE APLICACIONES SET CODEMPRESA_DEFECTO = ? WHERE APLICACION = ?",
            (codempresa or None, aplicacion),
        )
        self.conn.commit()

    def delete_aplicacion(self, aplicacion: str) -> None:
        self.conn.execute("DELETE FROM APLICACIONES WHERE APLICACION = ?", (aplicacion,))
        self.conn.commit()

    def get_aplicacion(self, aplicacion: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM APLICACIONES WHERE APLICACION = ?", (aplicacion,)
        ).fetchone()
        return dict(row) if row else None

    def list_aplicaciones(self, solo_activas: bool = False) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM APLICACIONES"
        if solo_activas:
            sql += " WHERE activo = 1"
        sql += " ORDER BY APLICACION"
        return [dict(r) for r in self.conn.execute(sql).fetchall()]

    # -- APLICACIONES_CAPTURAS ---------------------------------------------

    def upsert_captura(
        self,
        aplicacion: str,
        nombre_campo: str,
        tipo: str,
        x: int,
        y: int,
        ancho: int,
        alto: int,
        ref_ancho: int,
        ref_alto: int,
        regex: Optional[str] = None,
    ) -> None:
        """Crea/actualiza la definición de una región a capturar para una app."""
        self.conn.execute(
            "INSERT INTO APLICACIONES_CAPTURAS "
            "(APLICACION, NOMBRE_CAMPO, TIPO, X, Y, ANCHO, ALTO, "
            " REF_ANCHO, REF_ALTO, REGEX) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(APLICACION, NOMBRE_CAMPO) DO UPDATE SET "
            "TIPO=excluded.TIPO, X=excluded.X, Y=excluded.Y, "
            "ANCHO=excluded.ANCHO, ALTO=excluded.ALTO, "
            "REF_ANCHO=excluded.REF_ANCHO, REF_ALTO=excluded.REF_ALTO, "
            "REGEX=excluded.REGEX",
            (aplicacion, nombre_campo, tipo, x, y, ancho, alto,
             ref_ancho, ref_alto, regex),
        )
        self.conn.commit()

    def get_capturas(self, aplicacion: str) -> List[Dict[str, Any]]:
        return [
            dict(r)
            for r in self.conn.execute(
                "SELECT * FROM APLICACIONES_CAPTURAS WHERE APLICACION = ? "
                "ORDER BY NOMBRE_CAMPO",
                (aplicacion,),
            ).fetchall()
        ]

    def delete_captura(self, captura_id: int) -> None:
        self.conn.execute(
            "DELETE FROM APLICACIONES_CAPTURAS WHERE id = ?", (captura_id,)
        )
        self.conn.commit()

    # -- PARTE_TRABAJO ------------------------------------------------------

    def open_segment(
        self,
        usuario: str,
        aplicacion: str,
        codempresa: Optional[str],
        informacion: Optional[str],
        tipo: str = "app",
        horainicio: Optional[str] = None,
    ) -> int:
        """Abre un nuevo segmento de trabajo (HORAFIN nulo). Devuelve su id."""
        cur = self.conn.execute(
            "INSERT INTO PARTE_TRABAJO "
            "(USUARIO, HORAINICIO, HORAFIN, APLICACION, INFORMACION, "
            " CODEMPRESA, TIPO, SINCRONIZADO) "
            "VALUES (?, ?, NULL, ?, ?, ?, ?, 0)",
            (usuario, horainicio or now_iso(), aplicacion, informacion,
             codempresa, tipo),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def delete_segment(self, segment_id: int) -> None:
        """Elimina un segmento (p. ej. demasiado corto para registrarse)."""
        self.conn.execute("DELETE FROM PARTE_TRABAJO WHERE id = ?", (segment_id,))
        self.conn.commit()

    def get_segment(self, segment_id: int) -> Optional[Dict[str, Any]]:
        """Devuelve un segmento por su id."""
        row = self.conn.execute(
            "SELECT * FROM PARTE_TRABAJO WHERE id = ?", (segment_id,)
        ).fetchone()
        return dict(row) if row else None

    def close_segment(self, segment_id: int, horafin: Optional[str] = None) -> None:
        """Cierra un segmento fijando su HORAFIN."""
        self.conn.execute(
            "UPDATE PARTE_TRABAJO SET HORAFIN = ? WHERE id = ?",
            (horafin or now_iso(), segment_id),
        )
        self.conn.commit()

    def get_open_segment(
        self, usuario: str
    ) -> Optional[Dict[str, Any]]:
        """Devuelve el segmento abierto (sin HORAFIN) más reciente del usuario."""
        row = self.conn.execute(
            "SELECT * FROM PARTE_TRABAJO "
            "WHERE USUARIO = ? AND HORAFIN IS NULL "
            "ORDER BY HORAINICIO DESC LIMIT 1",
            (usuario,),
        ).fetchone()
        return dict(row) if row else None

    def update_segment(
        self,
        segment_id: int,
        codempresa: Optional[str] = None,
        informacion: Optional[str] = None,
    ) -> None:
        """Corrige empresa/información de un segmento (edición manual)."""
        self.conn.execute(
            "UPDATE PARTE_TRABAJO SET CODEMPRESA = ?, INFORMACION = ? WHERE id = ?",
            (codempresa, informacion, segment_id),
        )
        self.conn.commit()

    def parte_del_dia(self, usuario: str, fecha: str) -> List[Dict[str, Any]]:
        """Segmentos del usuario cuya HORAINICIO cae en la fecha dada (YYYY-MM-DD)."""
        return [
            dict(r)
            for r in self.conn.execute(
                "SELECT * FROM PARTE_TRABAJO "
                "WHERE USUARIO = ? AND substr(HORAINICIO, 1, 10) = ? "
                "ORDER BY HORAINICIO",
                (usuario, fecha),
            ).fetchall()
        ]

    def last_closed_segment(self, usuario: str) -> Optional[Dict[str, Any]]:
        """Último segmento cerrado del usuario (el de HORAFIN más reciente)."""
        row = self.conn.execute(
            "SELECT * FROM PARTE_TRABAJO "
            "WHERE USUARIO = ? AND HORAFIN IS NOT NULL "
            "ORDER BY HORAFIN DESC LIMIT 1",
            (usuario,),
        ).fetchone()
        return dict(row) if row else None

    def reopen_segment(self, segment_id: int) -> None:
        """Reabre un segmento cerrado (HORAFIN = NULL) para reanudarlo."""
        self.conn.execute(
            "UPDATE PARTE_TRABAJO SET HORAFIN = NULL WHERE id = ?", (segment_id,)
        )
        self.conn.commit()

    def pendientes_sincronizar(self) -> List[Dict[str, Any]]:
        """Segmentos cerrados aún no sincronizados."""
        return [
            dict(r)
            for r in self.conn.execute(
                "SELECT * FROM PARTE_TRABAJO "
                "WHERE SINCRONIZADO = 0 AND HORAFIN IS NOT NULL "
                "ORDER BY HORAINICIO"
            ).fetchall()
        ]

    def marcar_sincronizados(self, ids: List[int]) -> None:
        if not ids:
            return
        self.conn.executemany(
            "UPDATE PARTE_TRABAJO SET SINCRONIZADO = 1 WHERE id = ?",
            [(i,) for i in ids],
        )
        self.conn.commit()

    # -- EVENTOS_CALENDARIO -------------------------------------------------

    def upsert_evento(
        self,
        usuario: str,
        inicio: str,
        fin: Optional[str],
        asunto: Optional[str],
        organizador: Optional[str],
        id_externo: str,
        origen: str,
    ) -> None:
        """Inserta o actualiza un evento de calendario (idempotente por id).

        No sobrescribe CODEMPRESA ni PARTE_ID: conserva la imputación manual.
        """
        self.conn.execute(
            "INSERT INTO EVENTOS_CALENDARIO "
            "(USUARIO, INICIO, FIN, ASUNTO, ORGANIZADOR, ID_EXTERNO, ORIGEN) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(ID_EXTERNO) DO UPDATE SET "
            "INICIO=excluded.INICIO, FIN=excluded.FIN, ASUNTO=excluded.ASUNTO, "
            "ORGANIZADOR=excluded.ORGANIZADOR, ORIGEN=excluded.ORIGEN",
            (usuario, inicio, fin, asunto, organizador, id_externo, origen),
        )
        self.conn.commit()

    def eventos_del_dia(self, usuario: str, fecha: str) -> List[Dict[str, Any]]:
        """Eventos de calendario cuyo INICIO cae en la fecha dada (YYYY-MM-DD)."""
        return [
            dict(r)
            for r in self.conn.execute(
                "SELECT * FROM EVENTOS_CALENDARIO "
                "WHERE USUARIO = ? AND substr(INICIO, 1, 10) = ? "
                "ORDER BY INICIO",
                (usuario, fecha),
            ).fetchall()
        ]

    def set_evento_empresa(
        self, evento_id: int, codempresa: Optional[str]
    ) -> None:
        self.conn.execute(
            "UPDATE EVENTOS_CALENDARIO SET CODEMPRESA = ? WHERE id = ?",
            (codempresa or None, evento_id),
        )
        self.conn.commit()

    def set_evento_parte(
        self, evento_id: int, parte_id: Optional[int], codempresa: Optional[str]
    ) -> None:
        """Enlaza una cita con el segmento de PARTE_TRABAJO creado al importarla
        (PARTE_ID nulo = cita no importada)."""
        self.conn.execute(
            "UPDATE EVENTOS_CALENDARIO SET PARTE_ID = ?, CODEMPRESA = ? "
            "WHERE id = ?",
            (parte_id, codempresa or None, evento_id),
        )
        self.conn.commit()

    # -- Utilidades ---------------------------------------------------------

    def table_counts(self) -> Dict[str, int]:
        return {
            t: self.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in TABLES
        }

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "WorkAuditDB":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Base de datos del módulo work-audit")
    parser.add_argument("--db-path", default=None, help="Ruta a work_audit.db")
    parser.add_argument("--init", action="store_true", help="Crear/actualizar esquema")
    parser.add_argument("--info", action="store_true", help="Mostrar ruta y conteos")
    args = parser.parse_args()

    db = WorkAuditDB(path=args.db_path)
    if args.init or not args.info:
        db.init_schema()
        print(f"✓ Esquema inicializado en: {db.path}")
    if args.info:
        print(f"Base de datos: {db.path}")
        for table, count in db.table_counts().items():
            print(f"  {table:<24} {count}")
    db.close()


if __name__ == "__main__":
    main()
