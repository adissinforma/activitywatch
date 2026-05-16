# 📊 ActivityWatch Database Inspector

Módulo de Python para inspeccionar y analizar la base de datos SQLite de ActivityWatch.

## 📋 Características

- ✅ Conectarse automáticamente a la base de datos por defecto
- ✅ Inspeccionar buckets (grupos de eventos)
- ✅ Consultar eventos con filtros (fechas, bucket específico)
- ✅ Obtener estadísticas de la base de datos
- ✅ Interfaz de línea de comandos
- ✅ API programática para integración en otros scripts

## 📁 Archivos

- **`db_inspector.py`** - Módulo principal con la clase `ActivityWatchDBInspector`
- **`examples_inspector.py`** - Ejemplos de uso
- **`README_INSPECTOR.md`** - Este archivo

## 🚀 Uso

### Línea de Comandos

```bash
# Inspección completa (estadísticas + buckets + eventos)
python db_inspector.py

# Solo estadísticas
python db_inspector.py --stats

# Solo buckets
python db_inspector.py --buckets

# Eventos con límite personalizado
python db_inspector.py --events --limit 20

# Eventos de un bucket específico
python db_inspector.py --events --bucket "aw-watcher-window"

# Eventos de las últimas N horas
python db_inspector.py --events --hours 2 --limit 30

# Usar base de datos personalizada
python db_inspector.py --db-path "C:\ruta\a\base_datos.db"
```

### Uso Programático

```python
from db_inspector import ActivityWatchDBInspector
from datetime import datetime, timedelta

# Inicializar
inspector = ActivityWatchDBInspector()

# 1. Obtener estadísticas
inspector.print_db_stats()

# 2. Obtener todos los buckets
buckets = inspector.get_buckets()
for bucket in buckets:
    print(f"Bucket: {bucket['id']}")
    print(f"  Tipo: {bucket['type']}")
    print(f"  Cliente: {bucket['client']}")

# 3. Contar eventos en un bucket
count = inspector.get_bucket_event_count("aw-watcher-window")
print(f"Eventos: {count}")

# 4. Obtener eventos recientes
events = inspector.get_events(
    bucket_id="aw-watcher-window",
    limit=10
)

for event in events:
    print(f"{event['timestamp']}: {event['data']}")

# 5. Filtrar por rango de fechas
end_time = datetime.now()
start_time = end_time - timedelta(hours=1)

recent_events = inspector.get_events(
    start_time=start_time,
    end_time=end_time,
    limit=50
)

# 6. Cerrar conexión
inspector.close()
```

## 🔍 API del Módulo

### Clase: `ActivityWatchDBInspector`

#### Constructor

```python
inspector = ActivityWatchDBInspector(db_path: Optional[str] = None)
```

**Parámetros:**
- `db_path` (opcional): Ruta a la base de datos. Si no se proporciona, busca en la ubicación por defecto.

**Excepciones:**
- `FileNotFoundError`: Si la base de datos no se encuentra

---

#### Métodos

##### `get_buckets() -> List[Dict]`

Obtiene todos los buckets de la base de datos.

**Retorna:** Lista de diccionarios con:
- `rowid`: ID interno
- `id`: Identificador único del bucket
- `name`: Nombre descriptivo
- `type`: Tipo de bucket (ej: "currentwindow", "afkstatus")
- `client`: Cliente/watcher que genera los datos
- `hostname`: Nombre de la máquina
- `created`: Fecha de creación (ISO8601)
- `data`: Datos adicionales en JSON

---

##### `get_events(bucket_id: Optional[str] = None, limit: int = 10, offset: int = 0, start_time: Optional[datetime] = None, end_time: Optional[datetime] = None) -> List[Dict]`

Obtiene eventos de la base de datos con filtros opcionales.

**Parámetros:**
- `bucket_id`: Filtrar por ID de bucket (opcional)
- `limit`: Número máximo de eventos (default: 10)
- `offset`: Número de eventos a saltar (default: 0)
- `start_time`: Filtrar por fecha inicial (datetime)
- `end_time`: Filtrar por fecha final (datetime)

**Retorna:** Lista de diccionarios con:
- `id`: ID del evento
- `timestamp`: Fecha/hora en ISO8601
- `duration_seconds`: Duración en segundos
- `data`: Datos del evento (app, ventana, etc.)

---

##### `get_bucket_event_count(bucket_id: str) -> int`

Obtiene el número de eventos en un bucket específico.

**Parámetros:**
- `bucket_id`: ID del bucket

**Retorna:** Número de eventos

---

##### `print_buckets_summary()`

Imprime un resumen formateado de todos los buckets.

---

##### `print_events(bucket_id: Optional[str] = None, limit: int = 10, start_time: Optional[datetime] = None, end_time: Optional[datetime] = None)`

Imprime eventos de forma legible.

**Parámetros:** Iguales a `get_events()`

---

##### `print_db_stats()`

Imprime estadísticas generales de la base de datos (tamaño, conteos, rango de fechas).

---

##### `close()`

Cierra la conexión a la base de datos.

## 📊 Estructura de Datos

### Bucket (Grupo de Eventos)

```json
{
  "id": "aw-watcher-window_hostname",
  "type": "currentwindow",
  "client": "aw-watcher-window",
  "hostname": "mi-pc",
  "created": "2024-05-16T10:30:00+00:00",
  "data": {
    "icon": "google-chrome"
  }
}
```

### Evento

```json
{
  "id": 12345,
  "timestamp": "2024-05-16T14:32:15.123456",
  "duration_seconds": 300.5,
  "data": {
    "app": "Google Chrome",
    "title": "GitHub - ActivityWatch",
    "class": "chromium-browser",
    "name": "google-chrome"
  }
}
```

## 🔗 Tipos de Buckets Comunes

| Bucket | Tipo | Datos |
|--------|------|-------|
| `aw-watcher-window` | `currentwindow` | Ventana activa, aplicación, título |
| `aw-watcher-afk` | `afkstatus` | Estado activo/inactivo |
| `aw-watcher-input` | `inputevents` | Eventos de teclado y mouse |

## 📍 Rutas de Base de Datos por SO

| SO | Ruta |
|----|----|
| Windows | `%APPDATA%\activitywatch\aw-server\sqlite.v1.db` |
| Linux | `~/.local/share/activitywatch/aw-server/sqlite.v1.db` |
| macOS | `~/Library/Application Support/activitywatch/aw-server/sqlite.v1.db` |

## 🔧 Ejemplos Completos

### Ejemplo 1: Estadísticas Básicas

```python
from db_inspector import ActivityWatchDBInspector

inspector = ActivityWatchDBInspector()
inspector.print_db_stats()
inspector.close()
```

### Ejemplo 2: Últimas 24 Horas de Actividad

```python
from db_inspector import ActivityWatchDBInspector
from datetime import datetime, timedelta

inspector = ActivityWatchDBInspector()

end_time = datetime.now()
start_time = end_time - timedelta(days=1)

events = inspector.get_events(
    start_time=start_time,
    end_time=end_time,
    limit=1000
)

total_duration = sum(e['duration_seconds'] for e in events)
print(f"Tiempo total: {total_duration / 3600:.1f} horas")

inspector.close()
```

### Ejemplo 3: Aplicaciones Más Usadas

```python
from db_inspector import ActivityWatchDBInspector
from collections import defaultdict

inspector = ActivityWatchDBInspector()

# Obtener eventos de ventana
events = inspector.get_events(
    bucket_id="aw-watcher-window",
    limit=10000
)

# Agrupar por aplicación
app_times = defaultdict(float)
for event in events:
    app = event['data'].get('app', 'Unknown')
    app_times[app] += event['duration_seconds']

# Ordenar por tiempo
sorted_apps = sorted(app_times.items(), key=lambda x: x[1], reverse=True)

print("Aplicaciones más usadas:")
for app, seconds in sorted_apps[:10]:
    hours = seconds / 3600
    print(f"  {app}: {hours:.1f} horas")

inspector.close()
```

## 🐛 Resolución de Problemas

### "Base de datos no encontrada"

Asegúrate de que ActivityWatch haya generado la base de datos. Ejecuta ActivityWatch primero para crear los archivos necesarios.

### Especificar ruta personalizada

```python
inspector = ActivityWatchDBInspector(
    db_path=r"C:\Users\tuusuario\AppData\Local\activitywatch\activitywatch\aw-server\sqlite.v1.db"
)
```

### Base de datos bloqueada

Si ActivityWatch está activo, la base de datos podría estar bloqueada. Intenta:
1. Cerrar ActivityWatch
2. O especificar modo lectura (los métodos get_* son de solo lectura)

## 📝 Notas

- La base de datos se guarda automáticamente en la carpeta de datos del usuario
- Los timestamps se almacenan en microsegundos internamente
- Los eventos se almacenan en orden descendente por timestamp
- La duración se almacena como diferencia entre starttime y endtime

## 📄 Licencia

Mismo que el proyecto ActivityWatch (MPL-2.0)
