"""OCR mediante el motor nativo de Windows (Windows.Media.Ocr).

No requiere instalación adicional: usa el OCR integrado en Windows 10/11
a través del paquete Python `winsdk`.
"""

import asyncio
import logging
import sys
from typing import Optional

from PIL import Image

log = logging.getLogger(__name__)

try:
    from winsdk.windows.graphics.imaging import (
        BitmapAlphaMode,
        BitmapPixelFormat,
        SoftwareBitmap,
    )
    from winsdk.windows.media.ocr import OcrEngine
    from winsdk.windows.security.cryptography import CryptographicBuffer

    _WINSDK = True
except ImportError:
    _WINSDK = False

_engine = None  # motor OCR cacheado


def _get_engine():
    """Devuelve el motor OCR (creado a partir de los idiomas del usuario)."""
    global _engine
    if not _WINSDK:
        return None
    if _engine is None:
        try:
            _engine = OcrEngine.try_create_from_user_profile_languages()
        except Exception as e:  # noqa: BLE001
            log.warning("No se pudo crear el motor OCR: %s", e)
            _engine = None
    return _engine


def is_available() -> bool:
    """Indica si el OCR nativo de Windows está disponible y operativo."""
    return _WINSDK and _get_engine() is not None


def _to_software_bitmap(img: Image.Image):
    """Convierte una imagen PIL a SoftwareBitmap BGRA8 para el motor OCR."""
    rgba = img.convert("RGBA")
    r, g, b, a = rgba.split()
    bgra = Image.merge("RGBA", (b, g, r, a))
    buffer = CryptographicBuffer.create_from_byte_array(bgra.tobytes())
    return SoftwareBitmap.create_copy_from_buffer(
        buffer,
        BitmapPixelFormat.BGRA8,
        img.width,
        img.height,
        BitmapAlphaMode.PREMULTIPLIED,
    )


async def _recognize(engine, bitmap) -> str:
    result = await engine.recognize_async(bitmap)
    return result.text if result else ""


def ocr_image(img: Image.Image, upscale: int = 2) -> str:
    """Reconoce el texto de una imagen. Devuelve cadena vacía si falla.

    Args:
        img: imagen PIL a procesar.
        upscale: factor de ampliación previo (mejora el OCR de texto pequeño).
    """
    engine = _get_engine()
    if engine is None:
        return ""
    try:
        if upscale > 1:
            img = img.resize(
                (img.width * upscale, img.height * upscale), Image.LANCZOS
            )
        bitmap = _to_software_bitmap(img)
        return asyncio.run(_recognize(engine, bitmap)).strip()
    except Exception as e:  # noqa: BLE001
        log.warning("Fallo de OCR: %s", e)
        return ""


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(f"OCR nativo de Windows disponible: {is_available()}")
    if len(sys.argv) > 1:
        texto = ocr_image(Image.open(sys.argv[1]))
        print(f"Texto reconocido:\n{texto!r}")
