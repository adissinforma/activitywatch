#!/usr/bin/env python3
"""
Database Inspector para ActivityWatch
Módulo para inspeccionar y analizar la base de datos de ActivityWatch.

Soporta tanto el esquema SQLite directo (aw-server-rust) como el esquema
Peewee ORM (aw-server Python), detectando automáticamente si los timestamps
están almacenados como microsegundos enteros o como cadenas ISO.
"""

import sqlite3
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Any
import argparse

# La consola de Windows usa cp1252 por defecto y no puede imprimir los
# caracteres Unicode (✓, 📦, ❌). Forzamos UTF-8 en la salida.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


class ActivityWatchDBInspector:
    """Clase para inspeccionar la base de datos de ActivityWatch"""

    def __init__(self, db_path: Optional[str] = None):
        """
        Inicializa el inspector con la ruta de la base de datos.

        Args:
            db_path: Ruta a la base de datos SQLite. Si no se proporciona,
                    busca en la ubicación por defecto.
        """
        if db_path is None:
            db_path = self._find_default_db()

        if db_path is None or not os.path.exists(db_path):
            raise FileNotFoundError(
                f"Base de datos no encontrada: {db_path or '(ninguna ruta detectada)'}"
            )

        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        print(f"✓ Conectado a: {self.db_path}")

        # Detectar esquema
        self._detect_schema()

    @staticmethod
    def _find_default_db() -> Optional[str]:
        """Busca la base de datos en las ubicaciones habituales."""
        possible_paths = [
            os.path.expandvars(r"%APPDATA%\activitywatch\aw-server\sqlite.v1.db"),
            os.path.expandvars(
                r"%LOCALAPPDATA%\activitywatch\activitywatch\aw-server\sqlite.v1.db"
            ),
        ]

        # También buscar archivos peewee en la ubicación de Local
        local_aw_path = os.path.expandvars(
            r"%LOCALAPPDATA%\activitywatch\activitywatch\aw-server"
        )
        if os.path.isdir(local_aw_path):
            for filename in sorted(os.listdir(local_aw_path)):
                if filename.startswith("peewee") and filename.endswith(".db"):
                    possible_paths.insert(0, os.path.join(local_aw_path, filename))

        for path in possible_paths:
            if os.path.exists(path):
                return path
        return None

    @staticmethod
    def _to_datetime(value: Any) -> Optional[datetime]:
        """
        Convierte un valor de timestamp a datetime (timezone-aware, UTC).

        Acepta microsegundos enteros (esquema antiguo) o cadenas ISO
        (esquema Peewee v2). Devuelve None si no se puede interpretar.
        """
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1_000_000, tz=timezone.utc)
        # Cadena ISO; SQLite puede usar separador espacio o 'T'.
        s = str(value).strip().replace(" ", "T", 1).replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    def _detect_schema(self):
        """Detecta el esquema de la base de datos (SQLite directo o Peewee ORM)."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}

        if "buckets" in tables and "events" in tables:
            self.schema_type = "sqlite"
            self.bucket_table = "buckets"
            self.bucket_pk = "rowid"
            self.bucket_col_data = "datastr"
            self.event_table = "events"
            self.event_col_data = "datastr"
            self.event_bucket_col = "bucketrow"
            self.event_time_start = "starttime"
            self.event_time_end = "endtime"
            self.event_has_duration = False
            self.event_time_is_text = False
            print("  Esquema: SQLite directo")
        elif {"bucketmodel", "bucket", "buckets"} & tables:
            bucket_table = next(
                t for t in ("bucketmodel", "bucket", "buckets") if t in tables
            )
            cursor.execute(f"PRAGMA table_info({bucket_table})")
            bucket_columns = {row[1] for row in cursor.fetchall()}

            self.schema_type = "peewee"
            self.bucket_table = bucket_table
            self.bucket_pk = "key" if "key" in bucket_columns else "id"
            self.bucket_col_data = (
                "json_data" if "json_data" in bucket_columns else "datastr"
            )

            event_table = next(
                t for t in ("eventmodel", "event", "events") if t in tables
            )
            self.event_table = event_table
            cursor.execute(f"PRAGMA table_info({event_table})")
            event_columns = {row[1] for row in cursor.fetchall()}

            self.event_col_data = (
                "json_data" if "json_data" in event_columns else "datastr"
            )
            self.event_bucket_col = "bucket_id"

            # Detectar columnas de tiempo
            if "start_time" in event_columns and "end_time" in event_columns:
                self.event_time_start = "start_time"
                self.event_time_end = "end_time"
                self.event_has_duration = False
            elif "timestamp" in event_columns and "duration" in event_columns:
                self.event_time_start = "timestamp"
                self.event_time_end = None  # se calcula con timestamp + duration
                self.event_has_duration = True
            else:
                raise ValueError(
                    f"No se encontraron columnas de tiempo en {event_table}. "
                    f"Columnas: {event_columns}"
                )

            # Detectar si los timestamps son texto ISO o microsegundos enteros
            cursor.execute(
                f"SELECT {self.event_time_start} FROM {event_table} LIMIT 1"
            )
            sample = cursor.fetchone()
            self.event_time_is_text = bool(sample) and isinstance(sample[0], str)

            print(
                f"  Esquema: Peewee ORM (bucket: {bucket_table}, event: {event_table}, "
                f"tiempo: {'ISO texto' if self.event_time_is_text else 'microsegundos'})"
            )
        else:
            raise ValueError(f"Esquema desconocido. Tablas disponibles: {tables}")

    def get_buckets(self) -> List[Dict[str, Any]]:
        """Obtiene todos los buckets de la base de datos."""
        cursor = self.conn.cursor()
        cursor.execute(
            f"SELECT {self.bucket_pk}, id, name, type, client, hostname, created, "
            f"{self.bucket_col_data} FROM {self.bucket_table}"
        )

        buckets = []
        for row in cursor.fetchall():
            buckets.append(
                {
                    "rowid": row[0],
                    "id": row[1],
                    "name": row[2],
                    "type": row[3],
                    "client": row[4],
                    "hostname": row[5],
                    "created": row[6],
                    "data": json.loads(row[7] or "{}"),
                }
            )
        return buckets

    def _bucket_rowid(self, bucket_id: str) -> Any:
        """Devuelve la clave primaria interna de un bucket a partir de su id."""
        cursor = self.conn.cursor()
        cursor.execute(
            f"SELECT {self.bucket_pk} FROM {self.bucket_table} WHERE id = ?",
            (bucket_id,),
        )
        result = cursor.fetchone()
        if not result:
            raise ValueError(f"Bucket no encontrado: {bucket_id}")
        return result[0]

    def get_events(
        self,
        bucket_id: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Obtiene eventos de la base de datos.

        Args:
            bucket_id: ID del bucket (opcional).
            limit: Número máximo de eventos a retornar.
            offset: Número de eventos a saltar.
            start_time: Filtrar por fecha inicial.
            end_time: Filtrar por fecha final.
        """
        cursor = self.conn.cursor()

        # Columnas a seleccionar
        if self.event_has_duration:
            select_cols = (
                f"id, {self.event_bucket_col}, {self.event_time_start}, "
                f"duration, {self.event_col_data}"
            )
        else:
            select_cols = (
                f"id, {self.event_bucket_col}, {self.event_time_start}, "
                f"{self.event_time_end}, {self.event_col_data}"
            )
        query = f"SELECT {select_cols} FROM {self.event_table}"

        params: List[Any] = []
        conditions: List[str] = []

        if bucket_id:
            conditions.append(f"{self.event_bucket_col} = ?")
            params.append(self._bucket_rowid(bucket_id))

        # Para acotar el rango filtramos siempre por el inicio del evento.
        col_start = self.event_time_start
        if start_time:
            if self.event_time_is_text:
                conditions.append(f"datetime({col_start}) >= datetime(?)")
                params.append(start_time.isoformat())
            else:
                conditions.append(f"{col_start} >= ?")
                params.append(int(start_time.timestamp() * 1_000_000))
        if end_time:
            if self.event_time_is_text:
                conditions.append(f"datetime({col_start}) <= datetime(?)")
                params.append(end_time.isoformat())
            else:
                conditions.append(f"{col_start} <= ?")
                params.append(int(end_time.timestamp() * 1_000_000))

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += f" ORDER BY {col_start} DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(query, params)

        events = []
        for row in cursor.fetchall():
            start_dt = self._to_datetime(row[2])

            if self.event_has_duration:
                duration = float(row[3] or 0)
                end_dt = start_dt + timedelta(seconds=duration) if start_dt else None
            else:
                end_dt = self._to_datetime(row[3])
                duration = (
                    (end_dt - start_dt).total_seconds()
                    if start_dt and end_dt
                    else 0.0
                )

            events.append(
                {
                    "id": row[0],
                    "bucket_row": row[1],
                    "timestamp": start_dt.isoformat() if start_dt else None,
                    "endtime": end_dt.isoformat() if end_dt else None,
                    "duration_seconds": duration,
                    "data": json.loads(row[4] or "{}"),
                }
            )
        return events

    def get_bucket_event_count(self, bucket_id: str) -> int:
        """Obtiene el número de eventos en un bucket."""
        cursor = self.conn.cursor()
        cursor.execute(
            f"SELECT COUNT(*) FROM {self.event_table} "
            f"WHERE {self.event_bucket_col} = ?",
            (self._bucket_rowid(bucket_id),),
        )
        return cursor.fetchone()[0]

    def print_buckets_summary(self):
        """Imprime un resumen de todos los buckets."""
        buckets = self.get_buckets()

        print("\n" + "=" * 100)
        print("BUCKETS DISPONIBLES")
        print("=" * 100)

        for bucket in buckets:
            event_count = self.get_bucket_event_count(bucket["id"])
            print(f"\n📦 Bucket: {bucket['id']}")
            print(f"   Nombre:      {bucket['name']}")
            print(f"   Tipo:        {bucket['type']}")
            print(f"   Cliente:     {bucket['client']}")
            print(f"   Hostname:    {bucket['hostname']}")
            print(f"   Creado:      {bucket['created']}")
            print(f"   Eventos:     {event_count}")
            if bucket["data"]:
                print(f"   Datos:       {json.dumps(bucket['data'], indent=17)}")

    def print_events(
        self,
        bucket_id: Optional[str] = None,
        limit: int = 10,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ):
        """Imprime eventos de forma legible."""
        events = self.get_events(
            bucket_id=bucket_id,
            limit=limit,
            start_time=start_time,
            end_time=end_time,
        )

        if not events:
            print("No se encontraron eventos.")
            return

        print("\n" + "=" * 150)
        print("EVENTOS")
        if bucket_id:
            print(f"Bucket: {bucket_id}")
        print("=" * 150)

        for i, event in enumerate(events, 1):
            print(f"\n📌 Evento #{i}")
            print(f"   ID:        {event['id']}")
            print(f"   Timestamp: {event['timestamp']}")
            print(f"   Duración:  {event['duration_seconds']:.2f} segundos")
            print(f"   Datos:     {json.dumps(event['data'], indent=14, ensure_ascii=False)}")

    def print_db_stats(self):
        """Imprime estadísticas de la base de datos."""
        cursor = self.conn.cursor()

        cursor.execute(f"SELECT COUNT(*) FROM {self.bucket_table}")
        bucket_count = cursor.fetchone()[0]

        cursor.execute(f"SELECT COUNT(*) FROM {self.event_table}")
        event_count = cursor.fetchone()[0]

        # Rango de fechas (MIN/MAX sobre la columna de inicio)
        start_dt = end_dt = None
        if event_count > 0:
            cursor.execute(
                f"SELECT MIN({self.event_time_start}), MAX({self.event_time_start}) "
                f"FROM {self.event_table}"
            )
            min_val, max_val = cursor.fetchone()
            start_dt = self._to_datetime(min_val)
            end_dt = self._to_datetime(max_val)

        print("\n" + "=" * 100)
        print("ESTADÍSTICAS DE LA BASE DE DATOS")
        print("=" * 100)
        print(f"Archivo:          {self.db_path}")
        print(f"Tamaño:           {os.path.getsize(self.db_path) / (1024 * 1024):.2f} MB")
        print(f"Esquema:          {self.schema_type.upper()}")
        print(f"Buckets:          {bucket_count}")
        print(f"Total de eventos: {event_count}")

        if start_dt and end_dt:
            print(f"Rango de datos:   {start_dt} a {end_dt}")
            print(f"Duración total:   {end_dt - start_dt}")
        print()

    def close(self):
        """Cierra la conexión a la base de datos."""
        self.conn.close()

    # Permite usar el inspector como context manager
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def main():
    """Función principal con interfaz de línea de comandos."""
    parser = argparse.ArgumentParser(
        description="Inspector de base de datos de ActivityWatch"
    )
    parser.add_argument("--db-path", help="Ruta a la base de datos SQLite", default=None)
    parser.add_argument("--buckets", action="store_true", help="Mostrar resumen de buckets")
    parser.add_argument("--events", action="store_true", help="Mostrar eventos")
    parser.add_argument("--bucket", help="Filtrar por ID de bucket")
    parser.add_argument(
        "--limit", type=int, default=10,
        help="Número máximo de eventos a mostrar (default: 10)",
    )
    parser.add_argument("--stats", action="store_true", help="Mostrar estadísticas de la BD")
    parser.add_argument(
        "--hours", type=int, help="Mostrar eventos de las últimas N horas"
    )

    args = parser.parse_args()

    try:
        with ActivityWatchDBInspector(db_path=args.db_path) as inspector:
            # Si no se especifica nada, mostrar todo
            if not any([args.buckets, args.events, args.stats]):
                args.buckets = args.events = args.stats = True

            if args.stats:
                inspector.print_db_stats()

            if args.buckets:
                inspector.print_buckets_summary()

            if args.events:
                start_time = end_time = None
                if args.hours:
                    end_time = datetime.now(timezone.utc)
                    start_time = end_time - timedelta(hours=args.hours)

                inspector.print_events(
                    bucket_id=args.bucket,
                    limit=args.limit,
                    start_time=start_time,
                    end_time=end_time,
                )
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
