# Prompt — Login Biloop + listado de empresas en work-audit

Pegar en Claude Code (o similar) ejecutándose dentro del repo `activitywatch`.

---

Incorpora a la app work-audit un login contra el portal Biloop, con opción de
recordar/olvidar credenciales, y muestra el listado de empresas autorizadas.

## Contexto (ya disponible)

- El cliente HTTP de Biloop ya está en `work_audit/biloop.py`. NO lo modifiques.
  API que debes usar:
    - `cli = biloop.BiloopClient(url, subscription_key)`
    - `token = cli.obtener_token(user, password)` — fallback SISTEMA→USUARIO automático
    - `empresas = cli.listar_empresas(token)` — `list[dict]`: companyId, name, cif, program…
    - `usuario = cli.obtener_usuario(token)` — dict del usuario logado (no crítico)
    - `biloop.BiloopError` — excepción a capturar
    - `biloop.diag_config(url, key)` — resumen URL+key para mensajes de error
- La configuración vive en `work_audit/config.py` (TOML, `%APPDATA%\activitywatch\work-audit\work-audit.toml`) con `load_config()`/`save_config()` y la lista `_CONFIG_KEYS`.
- La UI usa PyQt6 con la estética de `work_audit/ui/style.py` (`STYLESHEET`, `HeaderBand`) y el patrón de `work_audit/ui/config_window.py`.

## Cambios en config.py

Añade estas claves a `DEFAULT_CONFIG` y a `_CONFIG_KEYS`:

    biloop_url               = ""      # URL base del portal, p.ej. https://auren.biloop.es
    biloop_subscription_key  = ""      # Subscription Key (UUID)
    biloop_key_tipo_usuario  = false   # true => key tipo USUARIO: no enviar USER/PASSWORD
    biloop_usuario           = ""      # último usuario, solo si "recordar" está activo
    biloop_recordar          = false   # recordar credenciales entre sesiones

IMPORTANTE — seguridad: la contraseña NO se guarda en el TOML en claro.
Guárdala en el Almacén de credenciales de Windows usando `win32cred` (pywin32 ya
es dependencia). Crea un helper `work_audit/credenciales.py` con:

- `guardar_password(usuario, password)` -> `win32cred.CredWrite`, target `"work-audit:biloop"`
- `leer_password(usuario)` -> `str | None`
- `olvidar_password(usuario)` -> `win32cred.CredDelete` (silencioso si no existe)

## UI — diálogo de login

Crea `work_audit/ui/biloop_login.py` con un QDialog "Acceso a Biloop" (estética
Outlook, reutiliza `STYLESHEET`/`HeaderBand`) que contenga:

- Campos: URL del portal, Subscription Key, Usuario, Contraseña (echo password).
- Checkbox "Mi API Key es de tipo USUARIO (no enviar credenciales al portal)".
  Cuando esté marcado, deshabilita Usuario/Contraseña.
- Checkbox "Recordar mis credenciales en este equipo".
- Botón "Entrar" y botón "Olvidar credenciales guardadas".

Al abrir el diálogo: precarga URL, key, tipo de key y usuario desde config; si
`biloop_recordar` es true, precarga la contraseña con `leer_password(usuario)`.

Al pulsar "Entrar":

1. Construye `BiloopClient(url, key)`. Si url o key vacías, avisa y no continúes.
2. user/pass = None si la key es tipo USUARIO; si no, los del formulario.
3. `token = cli.obtener_token(user, pass)` y `empresas = cli.listar_empresas(token)`,
   mostrando un cursor de espera / mensaje "Conectando con Biloop…".
4. Captura `biloop.BiloopError`: muestra un QMessageBox con el mensaje del error
   y, debajo, `biloop.diag_config(url, key)`. No cierres el diálogo.
5. Si va bien: guarda en config url, key, tipo de key, `biloop_recordar` y
   `biloop_usuario` (usuario solo si "recordar" está marcado). Si "recordar" está
   marcado y la key NO es tipo usuario, `guardar_password(usuario, pass)`; si no,
   `olvidar_password(usuario)`. Cierra el diálogo con `accept()` y expón al llamante
   la lista de empresas y el token (p.ej. `self.empresas` / `self.token`).

Botón "Olvidar credenciales guardadas": `olvidar_password(usuario)`, pone
`biloop_recordar=false` y `biloop_usuario=""` en config, limpia los campos del
formulario y confirma con un mensaje.

## Listado de empresas

Tras un login correcto, muestra las empresas en una QTableWidget con el estilo
de las tablas de `config_window.py` (`_style_table`): columnas Código (companyId),
Nombre (name), CIF (cif), Programa (program). Ordénalas por nombre.
Puede ser una pestaña nueva en la ventana de configuración o una ventana propia
abierta al cerrar el diálogo de login — elige lo que encaje mejor con la
navegación actual (`tray.py` / `__main__.py`) y deja un comentario explicando la
decisión.

## Integración

Añade un punto de entrada para abrir el login (entrada en el menú del tray
`work_audit/ui/tray.py`, o un botón en la ventana de configuración). No rompas
el arranque actual: si no hay configuración Biloop, la app debe seguir
funcionando igual que ahora.

## Criterios de aceptación

- Primer arranque sin config: el login abre con todos los campos vacíos.
- Con "recordar" activo: al reabrir el login, URL/key/usuario/contraseña vienen
  precargados y "Entrar" funciona sin reescribir nada.
- "Olvidar credenciales": tras pulsarlo, reabrir el login muestra la contraseña
  vacía y `biloop_recordar=false` en el TOML.
- La contraseña nunca aparece en `work-audit.toml`.
- Errores de Biloop (URL mala, key inválida, usuario rechazado, red caída) se
  muestran de forma legible sin cerrar el diálogo ni dejar la app colgada.
- Tras login OK se ve la tabla de empresas con Código/Nombre/CIF/Programa.
