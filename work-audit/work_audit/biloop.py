"""
biloop.py
Cliente HTTP del portal Biloop / SuiteLoop. Equivalente al `BiloopApiClient.cs`
de la app ExportaMDB. Solo se usan dos endpoints:

    GET  {url}/api-global/v1/token         → JWT (TTL 2h)
    GET  {url}/api-global/v1/getCompanies  → empresas con permiso para el usuario

Cabeceras canónicas (en MAYÚSCULAS, no son `Ocp-Apim-Subscription-Key`):

    SUBSCRIPTION_KEY  : siempre
    USER / PASSWORD   : solo cuando la key es de tipo SISTEMA
    token             : (minúscula) en /getCompanies, con el JWT obtenido

La app no sabe a priori si la subscription key es de tipo SISTEMA (necesita
USER+PASSWORD) o USUARIO (rechaza esas cabeceras). Por eso `obtener_token`
intenta primero con credenciales y, si Biloop las rechaza, reintenta sin
ellas — exactamente igual que el cliente .NET.
"""
from __future__ import annotations

import base64
import json
import logging
from typing import Optional

import requests

log = logging.getLogger(__name__)

_TIMEOUT_S = 30


class BiloopError(Exception):
    """Error devuelto por el portal Biloop o por la red al hablar con él."""


def _mask_key(key: str) -> str:
    if not key:
        return "<vacía>"
    if len(key) <= 12:
        return f"<corta:{len(key)} chars>"
    return f"{key[:8]}...{key[-4:]} ({len(key)} chars)"


def _truncar(s: str, n: int) -> str:
    if not s:
        return ""
    return s if len(s) <= n else s[:n] + "..."


def decodificar_jwt_payload(token: str) -> dict:
    """Decodifica el *payload* (claims) de un JWT sin verificar la firma.

    Útil para leer información pública del token (p. ej. `user_id`, `email`)
    sin necesidad de la clave del emisor. El emisor sigue siendo el único
    que puede *generar* tokens válidos; aquí solo *interpretamos* los que
    nos llegan ya autenticados por el portal.
    """
    if not token:
        return {}
    partes = token.split(".")
    if len(partes) < 2:
        return {}
    payload_b64 = partes[1]
    # JWT usa base64url (RFC 7515), hay que rellenar el padding antes de decodificar.
    padding = "=" * (-len(payload_b64) % 4)
    try:
        payload_bytes = base64.urlsafe_b64decode(payload_b64 + padding)
        data = json.loads(payload_bytes.decode("utf-8", errors="replace"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _extraer_user_id(token: str) -> Optional[int]:
    """Extrae el `user_id` del JWT probando los claims más típicos."""
    claims = decodificar_jwt_payload(token)
    for k in ("user_id", "userId", "id", "uid", "sub"):
        v = claims.get(k)
        if v is None or v == "":
            continue
        try:
            return int(v)
        except (TypeError, ValueError):
            continue
    return None


def _normalizar_url(url: str) -> str:
    u = (url or "").strip().rstrip("/")
    if not u:
        raise ValueError("URL del portal vacía")
    if not u.lower().startswith(("http://", "https://")):
        u = "https://" + u
    return u


class BiloopClient:
    """Cliente del portal Biloop."""

    def __init__(self, url: str, subscription_key: str):
        if not subscription_key or not subscription_key.strip():
            raise ValueError("Subscription key vacía")
        self.base_url = _normalizar_url(url)
        self.subscription_key = subscription_key.strip()

    # ------------------------------------------------------------------
    # Token
    # ------------------------------------------------------------------
    def obtener_token(
        self,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ) -> str:
        """Devuelve un JWT del portal.

        Si se pasan credenciales (key tipo SISTEMA) las usa; si Biloop las
        rechaza reintenta sin ellas (key tipo USUARIO). Si ambos intentos
        fallan, levanta BiloopError con el detalle de los dos errores.
        """
        hay_creds = bool(user) or bool(password)
        error_con_creds: Optional[str] = None

        if hay_creds:
            try:
                return self._intentar_token(user, password)
            except BiloopError as e:
                error_con_creds = str(e)

        try:
            return self._intentar_token(None, None)
        except BiloopError as e:
            if error_con_creds is not None:
                raise BiloopError(
                    "[BAC#BOTH] Biloop rechazó ambos intentos:\n"
                    f"  · Con USER/PASSWORD: {error_con_creds}\n"
                    f"  · Solo con SUBSCRIPTION_KEY: {e}"
                )
            raise

    def _intentar_token(
        self,
        user: Optional[str],
        password: Optional[str],
    ) -> str:
        url = f"{self.base_url}/api-global/v1/token"
        headers = {
            "SUBSCRIPTION_KEY": self.subscription_key,
            "Accept": "application/json",
        }
        if user:
            headers["USER"] = user
        if password:
            headers["PASSWORD"] = password

        log.info(
            "[BILOOP] >>> GET %s · USER=%s · PASSWORD=%s · KEY=%s",
            url,
            user or "<vacío>",
            f"<{len(password)} chars>" if password else "<vacío>",
            _mask_key(self.subscription_key),
        )

        try:
            resp = requests.get(
                url, headers=headers, timeout=_TIMEOUT_S, allow_redirects=False
            )
        except requests.RequestException as e:
            raise BiloopError(f"[BAC#NET] Error de red contra {url}: {e}") from e

        body = resp.text or ""
        log.info(
            "[BILOOP] <<< %s %s · body(%d chars): %s",
            resp.status_code,
            resp.reason,
            len(body),
            _truncar(body, 800),
        )

        if not resp.ok:
            raise BiloopError(
                f"[BAC#HTTP] HTTP {resp.status_code} en /token: {_truncar(body, 240)}"
            )

        try:
            parsed = resp.json()
        except ValueError as e:
            raise BiloopError(
                f"[BAC#JSON] /token devolvió no-JSON: {_truncar(body, 240)}"
            ) from e

        if not isinstance(parsed, dict):
            raise BiloopError("[BAC#NULL] Respuesta /token vacía o ilegible.")

        if str(parsed.get("status", "")).upper() != "OK":
            base_msg = parsed.get("message") or "Biloop denegó el acceso (status=KO)."
            raise BiloopError(
                f"{base_msg}\n"
                f"URL atacada: {url}\n"
                f"Respuesta cruda: {_truncar(body, 800)}"
            )

        data = parsed.get("data") or {}
        token = data.get("token")
        if not token:
            raise BiloopError("[BAC#NOTOKEN] Biloop OK pero sin token en la respuesta.")
        return token

    # ------------------------------------------------------------------
    # Empresas
    # ------------------------------------------------------------------
    def listar_empresas(self, token: str) -> list[dict]:
        """Devuelve la lista de empresas con permiso para el token dado.

        Cada elemento es un dict con (al menos): companyId, name, cif,
        program, companyIdReal, companyIdNom. Otros campos del modelo se
        ignoran silenciosamente.
        """
        url = f"{self.base_url}/api-global/v1/getCompanies"
        headers = {
            "SUBSCRIPTION_KEY": self.subscription_key,
            "Accept": "application/json",
        }
        if token:
            headers["token"] = token

        log.info(
            "[BILOOP] >>> GET %s · KEY=%s · token=%s",
            url, _mask_key(self.subscription_key), _mask_key(token or ""),
        )

        try:
            resp = requests.get(
                url, headers=headers, timeout=_TIMEOUT_S, allow_redirects=False
            )
        except requests.RequestException as e:
            raise BiloopError(f"Error de red contra {url}: {e}") from e

        body = resp.text or ""
        log.info(
            "[BILOOP] <<< %s %s · body(%d chars)",
            resp.status_code, resp.reason, len(body),
        )

        if not resp.ok:
            raise BiloopError(
                f"HTTP {resp.status_code} en /getCompanies: {_truncar(body, 240)}"
            )

        try:
            parsed = resp.json()
        except ValueError as e:
            raise BiloopError(
                f"/getCompanies devolvió no-JSON: {_truncar(body, 240)}"
            ) from e

        if not isinstance(parsed, dict):
            raise BiloopError("Respuesta /getCompanies vacía o ilegible.")

        if str(parsed.get("status", "")).upper() != "OK":
            msg = parsed.get("message") or "Biloop denegó /getCompanies"
            raise BiloopError(f"Biloop: {msg}")

        return parsed.get("data") or []

    # ------------------------------------------------------------------
    # Diagnóstico
    # ------------------------------------------------------------------
    def probar_credenciales(
        self,
        user: Optional[str],
        password: Optional[str],
    ) -> tuple[bool, str]:
        """Intento único contra ``/token`` con las credenciales dadas, sin
        la lógica de fallback de :meth:`obtener_token`. Útil para probar
        formatos de usuario en herramientas de diagnóstico.

        Devuelve ``(True, "OK · token NN chars")`` o
        ``(False, "<mensaje de error>")``.
        """
        try:
            token = self._intentar_token(user, password)
            return True, f"OK · token {len(token)} chars"
        except BiloopError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Error inesperado: {type(e).__name__}: {e}"

    # ------------------------------------------------------------------
    # Usuario logado
    # ------------------------------------------------------------------
    def obtener_usuario(
        self,
        token: str,
        user_id: Optional[int] = None,
        with_rules: bool = False,
        with_companies: bool = False,
    ) -> dict:
        """Devuelve la información del usuario.

        Endpoint: ``GET /api-global/v1/getUser?user_id=N``. Parámetros
        adicionales documentados por Biloop:
            * ``with_rules=1``     incluye reglas asociadas al usuario.
            * ``with_companies=1`` incluye empresas a las que tiene acceso.

        Si no se pasa ``user_id``, se intenta extraer del JWT (claims
        ``user_id``/``id``/``sub``). Si tampoco aparece allí, se levanta
        ``BiloopError``.

        La respuesta canónica de Biloop es ``{status, message, data}``;
        ``data`` suele ser un dict (con name/nif/email/role…) y a veces
        una lista de un único elemento. Devolvemos siempre dict (vacío
        si no hay datos) para que el caller pueda hacer ``.get()`` con
        seguridad.
        """
        if user_id is None:
            user_id = _extraer_user_id(token)
        if user_id is None:
            raise BiloopError(
                "[BAC#NOID] No se ha podido extraer `user_id` del JWT. "
                "Pásalo explícitamente o revisa los claims del token."
            )

        url = f"{self.base_url}/api-global/v1/getUser"
        params = {"user_id": int(user_id)}
        if with_rules:
            params["with_rules"] = 1
        if with_companies:
            params["with_companies"] = 1

        headers = {
            "SUBSCRIPTION_KEY": self.subscription_key,
            "Accept": "application/json",
        }
        if token:
            headers["token"] = token

        log.info(
            "[BILOOP] >>> GET %s?user_id=%s · KEY=%s · token=%s",
            url, user_id,
            _mask_key(self.subscription_key), _mask_key(token or ""),
        )

        try:
            resp = requests.get(
                url, headers=headers, params=params,
                timeout=_TIMEOUT_S, allow_redirects=False,
            )
        except requests.RequestException as e:
            raise BiloopError(f"Error de red contra {url}: {e}") from e

        body = resp.text or ""
        log.info(
            "[BILOOP] <<< %s %s · body(%d chars): %s",
            resp.status_code, resp.reason, len(body), _truncar(body, 600),
        )

        if not resp.ok:
            raise BiloopError(
                f"HTTP {resp.status_code} en /getUser: {_truncar(body, 240)}"
            )

        try:
            parsed = resp.json()
        except ValueError as e:
            raise BiloopError(
                f"/getUser devolvió no-JSON: {_truncar(body, 240)}"
            ) from e

        if not isinstance(parsed, dict):
            raise BiloopError("Respuesta /getUser vacía o ilegible.")

        if str(parsed.get("status", "")).upper() != "OK":
            msg = parsed.get("message") or "Biloop denegó /getUser"
            raise BiloopError(f"Biloop: {msg}")

        data = parsed.get("data")
        # Algunos despliegues devuelven `data` como lista con un elemento.
        if isinstance(data, list):
            data = data[0] if data else {}
        if not isinstance(data, dict):
            data = {}
        return data

    # ------------------------------------------------------------------
    # Helper de alto nivel
    # ------------------------------------------------------------------
    def cifs_autorizados(
        self,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ) -> set[str]:
        """Hace token + listar_empresas y devuelve el set normalizado de CIFs
        (uppercase, sin espacios). Útil para usarlo como filtro contra la
        tabla EMPRESAS de SQL Server."""
        token = self.obtener_token(user, password)
        empresas = self.listar_empresas(token)
        cifs: set[str] = set()
        for c in empresas:
            cif = (c.get("cif") or "").strip().upper()
            if cif:
                cifs.add(cif)
        return cifs


def diag_config(url: str, subscription_key: str) -> str:
    """Resumen para errores de UI: muestra la URL exacta y un fragmento de
    la key (primeros/últimos chars) para detectar typos sin revelar el
    secreto entero."""
    return (
        f"URL portal: {url or '(vacío)'}\n"
        f"Key (parcial): {_mask_key(subscription_key or '')}"
    )
