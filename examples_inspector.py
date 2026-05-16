#!/usr/bin/env python3
"""
Ejemplos de uso del módulo db_inspector
"""

from db_inspector import ActivityWatchDBInspector
from datetime import datetime, timedelta


def example_1_basic_inspection():
    """Ejemplo 1: Inspección básica"""
    print("\n" + "="*80)
    print("EJEMPLO 1: Inspección Básica")
    print("="*80)
    
    inspector = ActivityWatchDBInspector()
    inspector.print_db_stats()
    inspector.print_buckets_summary()
    inspector.close()


def example_2_get_events_from_bucket():
    """Ejemplo 2: Obtener eventos de un bucket específico"""
    print("\n" + "="*80)
    print("EJEMPLO 2: Eventos de un Bucket Específico")
    print("="*80)
    
    inspector = ActivityWatchDBInspector()
    
    # Primero, obtener los buckets disponibles
    buckets = inspector.get_buckets()
    
    if buckets:
        # Usar el primer bucket
        bucket_id = buckets[0]["id"]
        print(f"\nObteniendo eventos del bucket: {bucket_id}\n")
        
        inspector.print_events(bucket_id=bucket_id, limit=5)
    
    inspector.close()


def example_3_recent_events():
    """Ejemplo 3: Obtener eventos de las últimas horas"""
    print("\n" + "="*80)
    print("EJEMPLO 3: Eventos Recientes")
    print("="*80)
    
    inspector = ActivityWatchDBInspector()
    
    # Eventos de las últimas 2 horas
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=2)
    
    print(f"\nEventos desde {start_time} hasta {end_time}\n")
    
    inspector.print_events(
        limit=20,
        start_time=start_time,
        end_time=end_time
    )
    
    inspector.close()


def example_4_programmatic_access():
    """Ejemplo 4: Acceso programático a los datos"""
    print("\n" + "="*80)
    print("EJEMPLO 4: Acceso Programático")
    print("="*80)
    
    inspector = ActivityWatchDBInspector()
    
    # Obtener todos los buckets
    buckets = inspector.get_buckets()
    print(f"\nTotal de buckets: {len(buckets)}")
    
    for bucket in buckets:
        count = inspector.get_bucket_event_count(bucket["id"])
        print(f"  - {bucket['id']}: {count} eventos")
    
    # Obtener eventos de forma programática
    print("\nÚltimos 3 eventos:")
    events = inspector.get_events(limit=3)
    
    for event in events:
        print(f"  - {event['timestamp']}: {event['data']}")
    
    inspector.close()


def example_5_query_specific_bucket():
    """Ejemplo 5: Consultar un bucket específico"""
    print("\n" + "="*80)
    print("EJEMPLO 5: Consulta de Bucket Específico")
    print("="*80)
    
    inspector = ActivityWatchDBInspector()
    
    # Buscar el bucket de ventana activa
    buckets = inspector.get_buckets()
    window_bucket = None
    
    for bucket in buckets:
        if "window" in bucket["type"].lower() or "currentwindow" in bucket["id"].lower():
            window_bucket = bucket["id"]
            break
    
    if window_bucket:
        print(f"\nBucket de ventana encontrado: {window_bucket}")
        count = inspector.get_bucket_event_count(window_bucket)
        print(f"Total de eventos: {count}\n")
        
        inspector.print_events(bucket_id=window_bucket, limit=10)
    else:
        print("No se encontró bucket de ventana")
    
    inspector.close()


if __name__ == "__main__":
    try:
        # Descomenta los ejemplos que quieras ejecutar
        
        example_1_basic_inspection()
        # example_2_get_events_from_bucket()
        # example_3_recent_events()
        # example_4_programmatic_access()
        # example_5_query_specific_bucket()
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
