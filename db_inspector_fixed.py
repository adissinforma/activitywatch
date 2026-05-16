#!/usr/bin/env python3
"""
Database Inspector para ActivityWatch
Módulo para inspeccionar y analizar la base de datos de ActivityWatch
"""

import sqlite3
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Any
import argparse


class ActivityWatchDBInspector:
    """Clase para inspeccionar la base de datos de ActivityWatch"""

    def __init__(self, db_path: Optional[str] = None):
        """
        Inicializa el inspector con la ruta de la base de datos
        
        Args:
            db_path: Ruta a la base de datos SQLite. Si no se proporciona,
                    busca en la ubicación por defecto.
        """
        if db_path is None:
            # Ubicaciones posibles en orden de preferencia
            possible_paths = [
                os.path.expandvars(r"%APPDATA%\activitywatch\aw-server\sqlite.v1.db"),
                os.path.expandvars(r"%LOCALAPPDATA%\activitywatch\activitywatch\aw-server\sqlite.v1.db"),
            ]
            
            # También buscar archivos peewee en la ubicación de Local
            local_aw_path = os.path.expandvars(r"%LOCALAPPDATA%\activitywatch\activitywatch\aw-server")
            if os.path.exists(local_aw_path):
                for filename in os.listdir(local_aw_path):
                    if filename.startswith("peewee") and filename.endswith(".db"):
                        possible_paths.insert(0, os.path.join(local_aw_path, filename))
            
            # Encontrar la primera ruta que existe
            db_path = None
            for path in possible_paths:
                if os.path.exists(path):
                    db_path = path
                    break
        
        self.db_path = db_path
        
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Base de datos no encontrada: {self.db_path}")
        
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        print(f"✓ Conectado a: {self.db_path}")
        
        # Detectar esquema
        self._detect_schema()
    
    def _detect_schema(self):
        """Detecta el esquema de la base de datos (SQLite directo o Peewee ORM)"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        
        if "buckets" in tables and "events" in tables:
            self.schema_type = "sqlite"
            self.bucket_table = "buckets"
            self.bucket_col_id = "id"
            self.bucket_col_data = "datastr"
            self.event_table = "events"
            self.event_col_data = "datastr"
            print(f"  Esquema: SQLite directo")
        elif "bucketmodel" in tables or "bucket" in tables or "buckets" in tables:
            # Peewee schema
            bucket_table = "bucketmodel" if "bucketmodel" in tables else ("bucket" if "bucket" in tables else "buckets")
            cursor.execute(f"PRAGMA table_info({bucket_table})")
            columns = {row[1] for row in cursor.fetchall()}
            
            self.schema_type = "peewee"
            self.bucket_table = bucket_table
            self.bucket_col_data = "json_data" if "json_data" in columns else "datastr"
            
            event_table = "eventmodel" if "eventmodel" in tables else ("event" if "event" in tables else "events")
            self.event_table = event_table
            self.event_col_data = "json_data" if "json_data" in columns else "datastr"
            self.event_bucket_col = "bucket_id"
            
            # Detectar nombres de columnas de tiempo en el event_table
            cursor.execute(f"PRAGMA table_info({event_table})")
            event_columns = {row[1] for row in cursor.fetchall()}
            
            if "start_time" in event_columns and "end_time" in event_columns:
                self.event_time_start = "start_time"
                self.event_time_end = "end_time"
                self.event_has_duration = False
            elif "timestamp" in event_columns and "duration" in event_columns:
                self.event_time_start = "timestamp"
                self.event_time_end = None  # Se calcula desde timestamp + duration
                self.event_has_duration = True
            else:
                raise ValueError(f"No se encontraron columnas de tiempo en {event_table}. Columnas: {event_columns}")
            
            print(f"  Esquema: Peewee ORM (bucket: {bucket_table}, event: {event_table})")
        else:
        else:
            raise ValueError(f"Esquema desconocido. Tablas disponibles: {tables}")
    
    def get_buckets(self) -> List[Dict[str, Any]]:
        """Obtiene todos los buckets de la base de datos"""
        cursor = self.conn.cursor()
        
        if self.schema_type == "sqlite":
            cursor.execute(
                f"SELECT rowid, id, name, type, client, hostname, created, {self.bucket_col_data} FROM {self.bucket_table}"
            )
        else:  # peewee
            cursor.execute(
                f"SELECT id, id, name, type, client, hostname, created, {self.bucket_col_data} FROM {self.bucket_table}"
            )
        
        buckets = []
        for row in cursor.fetchall():
            bucket = {
                "rowid": row[0],
                "id": row[1],
                "name": row[2],
                "type": row[3],
                "client": row[4],
                "hostname": row[5],
                "created": row[6],
                "data": json.loads(row[7] or "{}"),
            }
            buckets.append(bucket)
        
        return buckets
    
    def get_events(
        self,
        bucket_id: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Obtiene eventos de la base de datos
        
        Args:
            bucket_id: ID del bucket (opcional)
            limit: Número máximo de eventos a retornar
            offset: Número de eventos a saltar
            start_time: Filtrar por fecha inicial
            end_time: Filtrar por fecha final
        """
        cursor = self.conn.cursor()
        
        bucket_rowid = None
        if bucket_id:
            # Obtener el id del bucket
            cursor.execute(f"SELECT id FROM {self.bucket_table} WHERE id = ?", (bucket_id,))
            result = cursor.fetchone()
            if not result:
                raise ValueError(f"Bucket no encontrado: {bucket_id}")
            bucket_rowid = result[0]
        
        # Construir la consulta según esquema
        if self.schema_type == "sqlite":
            query = f"SELECT id, bucketrow, starttime, endtime, {self.event_col_data} FROM {self.event_table}"
            time_col_start = "starttime"
            time_col_end = "endtime"
            bucket_col = "bucketrow"
        else:  # peewee
            if hasattr(self, 'event_has_duration') and self.event_has_duration:
                # timestamp + duration
                query = f"SELECT id, {self.event_bucket_col}, {self.event_time_start}, duration, {self.event_col_data} FROM {self.event_table}"
                time_col_start = self.event_time_start
                time_col_end = None  # Calcular de timestamp + duration
            else:
                # start_time + end_time
                query = f"SELECT id, {self.event_bucket_col}, {self.event_time_start}, {self.event_time_end}, {self.event_col_data} FROM {self.event_table}"
                time_col_start = self.event_time_start
                time_col_end = self.event_time_end
            
            bucket_col = self.event_bucket_col
        
        params: List[Any] = []
        conditions = []
        
        if bucket_id:
            conditions.append(f"{bucket_col} = ?")
            params.append(bucket_rowid)
        
        if start_time:
            # Convertir a microsegundos (como en ActivityWatch)
            start_micros = int(start_time.timestamp() * 1_000_000)
            conditions.append(f"{time_col_start} >= ?")
            params.append(start_micros)
        
        if end_time:
            end_micros = int(end_time.timestamp() * 1_000_000)
            conditions.append(f"{time_col_end} <= ?")
            params.append(end_micros)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += f" ORDER BY {time_col_start} DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        
        events = []
        for row in cursor.fetchall():
            # Convertir microsegundos a datetime
            start_dt = datetime.fromtimestamp(row[2] / 1_000_000)
            
            # Calcular end_dt dependiendo del esquema
            if hasattr(self, 'event_has_duration') and self.event_has_duration:
                # duration está en segundos
                duration = row[3]
                end_dt = start_dt + timedelta(seconds=duration)
            else:
                # endtime en microsegundos
                end_dt = datetime.fromtimestamp(row[3] / 1_000_000)
                duration = (end_dt - start_dt).total_seconds()
            
            event = {
                "id": row[0],
                "bucket_row": row[1],
                "timestamp": start_dt.isoformat(),
                "endtime": end_dt.isoformat(),
                "duration_seconds": duration,
                "data": json.loads(row[4]),
            }
            events.append(event)
        
        return events
    
    def get_bucket_event_count(self, bucket_id: str) -> int:
        """Obtiene el número de eventos en un bucket"""
        cursor = self.conn.cursor()
        cursor.execute(f"SELECT id FROM {self.bucket_table} WHERE id = ?", (bucket_id,))
        result = cursor.fetchone()
        
        if not result:
            raise ValueError(f"Bucket no encontrado: {bucket_id}")
        
        bucket_row_id = result[0]
        
        if self.schema_type == "sqlite":
            cursor.execute(f"SELECT COUNT(*) FROM {self.event_table} WHERE bucketrow = ?", (bucket_row_id,))
        else:  # peewee
            cursor.execute(f"SELECT COUNT(*) FROM {self.event_table} WHERE bucket_id = ?", (bucket_row_id,))
        
        return cursor.fetchone()[0]
    
    def print_buckets_summary(self):
        """Imprime un resumen de todos los buckets"""
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
            if bucket['data']:
                print(f"   Datos:       {json.dumps(bucket['data'], indent=17)}")
    
    def print_events(
        self,
        bucket_id: Optional[str] = None,
        limit: int = 10,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ):
        """Imprime eventos de forma legible"""
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
            print(f"   ID:       {event['id']}")
            print(f"   Timestamp: {event['timestamp']}")
            print(f"   Duración: {event['duration_seconds']:.2f} segundos")
            print(f"   Datos:    {json.dumps(event['data'], indent=13)}")
    
    def print_db_stats(self):
        """Imprime estadísticas de la base de datos"""
        cursor = self.conn.cursor()
        
        # Total de buckets
        cursor.execute(f"SELECT COUNT(*) FROM {self.bucket_table}")
        bucket_count = cursor.fetchone()[0]
        
        # Total de eventos
        cursor.execute(f"SELECT COUNT(*) FROM {self.event_table}")
        event_count = cursor.fetchone()[0]
        
        # Rango de fechas
        if self.schema_type == "sqlite":
            cursor.execute(f"SELECT MIN(starttime), MAX(endtime) FROM {self.event_table}")
        else:  # peewee
            if hasattr(self, 'event_has_duration') and self.event_has_duration:
                cursor.execute(f"SELECT MIN({self.event_time_start}), MAX({self.event_time_start}) FROM {self.event_table}")
            else:
                cursor.execute(f"SELECT MIN({self.event_time_start}), MAX({self.event_time_end}) FROM {self.event_table}")
        
        time_result = cursor.fetchone()
        min_time, max_time = time_result if time_result else (None, None)
        
        print("\n" + "=" * 100)
        print("ESTADÍSTICAS DE LA BASE DE DATOS")
        print("=" * 100)
        print(f"Archivo:         {self.db_path}")
        print(f"Tamaño:          {os.path.getsize(self.db_path) / (1024 * 1024):.2f} MB")
        print(f"Esquema:         {self.schema_type.upper()}")
        print(f"Buckets:         {bucket_count}")
        print(f"Total de eventos: {event_count}")
        
        if min_time and max_time:
            start_dt = datetime.fromtimestamp(min_time / 1_000_000)
            end_dt = datetime.fromtimestamp(max_time / 1_000_000)
            duration = end_dt - start_dt
            print(f"Rango de datos:  {start_dt} a {end_dt}")
            print(f"Duración total:  {duration}")
        print()
    
    def close(self):
        """Cierra la conexión a la base de datos"""
        self.conn.close()


def main():
    """Función principal con interfaz de línea de comandos"""
    parser = argparse.ArgumentParser(
        description="Inspector de base de datos de ActivityWatch"
    )
    parser.add_argument(
        "--db-path",
        help="Ruta a la base de datos SQLite",
        default=None,
    )
    parser.add_argument(
        "--buckets",
        action="store_true",
        help="Mostrar resumen de buckets",
    )
    parser.add_argument(
        "--events",
        action="store_true",
        help="Mostrar eventos",
    )
    parser.add_argument(
        "--bucket",
        help="Filtrar por ID de bucket",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Número máximo de eventos a mostrar (default: 10)",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Mostrar estadísticas de la base de datos",
    )
    parser.add_argument(
        "--hours",
        type=int,
        help="Mostrar eventos de las últimas N horas",
    )
    
    args = parser.parse_args()
    
    try:
        inspector = ActivityWatchDBInspector(db_path=args.db_path)
        
        # Si no se especifica nada, mostrar todo
        if not any([args.buckets, args.events, args.stats]):
            args.buckets = True
            args.events = True
            args.stats = True
        
        if args.stats:
            inspector.print_db_stats()
        
        if args.buckets:
            inspector.print_buckets_summary()
        
        if args.events:
            start_time = None
            end_time = None
            
            if args.hours:
                end_time = datetime.now()
                start_time = end_time - timedelta(hours=args.hours)
            
            inspector.print_events(
                bucket_id=args.bucket,
                limit=args.limit,
                start_time=start_time,
                end_time=end_time,
            )
        
        inspector.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        exit(1)


if __name__ == "__main__":
    main()

