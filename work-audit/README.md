# work-audit · Auditoría de Trabajos y Parte Diario Semi-Automático

Módulo construido sobre [ActivityWatch](https://activitywatch.net). Además de
los tiempos por aplicación que ya registra ActivityWatch, deduce **para qué
empresa** se está trabajando dentro de ciertas aplicaciones (ERP, gestión…)
mediante capturas + OCR de regiones de pantalla, y genera un **parte de
trabajo diario** imputable por empresa.

## Cómo funciona

El propósito es medir el tiempo que se dedica a cada empresa cliente, y todo
el trabajo se imputa a alguna empresa.

1. Un servicio en segundo plano sondea la ventana en primer plano y registra
   **toda** la actividad en `PARTE_TRABAJO` (usuario, app, empresa, inicio, fin).
2. La empresa de cada segmento se asigna así:
   - **Apps auditadas** (con regiones de captura): se hace OCR de las regiones
     y se resuelve la empresa; si no se resuelve, queda en blanco para que el
     usuario la rellene.
   - **Apps no auditadas** (Chrome, Code…): empresa por defecto — la fijada
     para esa app o, si no hay, la global de la configuración.
3. El tiempo de **inactividad (AFK)** no se registra como trabajo.
4. Las apps de **reunión** (Teams, Zoom…) se marcan como tales; los eventos
   del **calendario configurado** (Outlook o Google) se muestran en la vista
   diaria y pueden importarse al parte con un clic.
5. Al arrancar el equipo se abre el **Parte Diario** con una vista de
   **calendario por horas** (estilo Outlook) y una pestaña de detalle; el
   usuario puede cambiar la empresa de cualquier bloque.

No modifica nada de ActivityWatch: usa su propia base de datos
(`work_audit.db`) y lee los tiempos de uso vía la API de AW.

## Requisitos

- Windows 10/11 (usa el OCR nativo de Windows).
- Python 3.11+.
- ActivityWatch en marcha (servidor en `localhost:5600`).

## Instalación

```sh
cd work-audit
pip install -e .
python -m work_audit.db --init          # crea la base de datos
python scripts/install_autostart.py     # abre el parte al iniciar sesión
```

## Uso

| Acción | Comando |
| --- | --- |
| Arrancar (auditor + bandeja + parte) | `python -m work_audit` |
| Arrancar sin abrir el parte | `python -m work_audit --no-report` |
| Parte diario (solo ventana) | `python -m work_audit.ui.daily_report` |
| Configuración / apps a auditar | `python -m work_audit.ui.config_window` |
| Marcar regiones de una app | `python -m work_audit.ui.region_trainer` |
| Auditor en consola (depuración) | `python -m work_audit.auditor` |
| Sincronizar empresas | `python -m work_audit.sync` |
| Inspeccionar la base de datos | `python -m work_audit.db --info` |

### Definir una aplicación a auditar

1. Abre **Configuración → Aplicaciones a auditar** y añade la aplicación
   (nombre del proceso, p. ej. `sage.exe`).
2. Pulsa **Marcar regiones…**: abre la aplicación real, pulsa *Capturar*
   (3 s de margen para activar su ventana) y dibuja rectángulos sobre las
   zonas donde aparece el código/nombre de empresa.
3. A cada región se le asigna un **tipo**:
   - `codempresa` — el texto es el código de empresa.
   - `nomempresa` — el texto es el nombre de la empresa.
   - `codigorelacion` — un identificador que se traduce a empresa mediante
     la tabla `EMPRESAS_APLICACION`.
4. Guarda. Con **Exportar seed** se vuelca la definición a
   `seed/capturas.seed.json` para distribuirla a otras instalaciones.

## Base de datos (`work_audit.db`)

`%LOCALAPPDATA%\activitywatch\activitywatch\work-audit\work_audit.db`

| Tabla | Contenido |
| --- | --- |
| `EMPRESAS` | Catálogo de empresas (se sincroniza desde un endpoint). |
| `EMPRESAS_APLICACION` | Relaciones código↔empresa por aplicación. |
| `APLICACIONES` | Aplicaciones con configuración propia (capturas y/o empresa por defecto). |
| `APLICACIONES_CAPTURAS` | Regiones de pantalla a capturar (definición común). |
| `PARTE_TRABAJO` | Segmentos de actividad imputables (resultado del módulo). |
| `EVENTOS_CALENDARIO` | Eventos importados del calendario de Outlook. |

## Configuración

`%APPDATA%\activitywatch\work-audit\work-audit.toml` (editable desde la
ventana de Configuración):

| Clave | Descripción |
| --- | --- |
| `usuario` | Usuario del parte (vacío = usuario de Windows). |
| `empresa_defecto` | Empresa por defecto global para apps no auditadas. |
| `poll_foreground` | Segundos entre sondeos de la ventana activa. |
| `capture_interval` | Segundos entre capturas periódicas de una app activa. |
| `merge_gap` | Hueco máximo (s) para fusionar segmentos consecutivos de la misma empresa. |
| `afk_timeout` | Segundos de inactividad tras los que el tiempo deja de contar. |
| `min_segment` | Duración mínima (s); los segmentos más cortos se descartan. |
| `apps_reunion` | Aplicaciones que se registran como reuniones. |
| `calendar_source` | Origen del calendario: `outlook`, `google` o `none`. |
| `google_credentials` | Ruta al `credentials.json` de Google (si el origen es Google). |
| `endpoint_empresas` | URL para sincronizar el catálogo de empresas. |
| `guardar_miniatura` | Guardar recorte de la región para verificación. |

## Privacidad

No se guardan capturas de pantalla completas: solo el texto OCR que justifica
la imputación y, opcionalmente, un recorte pequeño de la región.

## Pendiente

- La subida del parte a un sistema externo (`sync.upload_partes`) está
  preparada pero a la espera del contrato del endpoint (URL, autenticación,
  formato JSON).
