"""Captura de regiones de pantalla de una ventana.

Las regiones se definen relativas al área de cliente de la ventana y al
tamaño que tenía al marcarlas (REF_ANCHO/REF_ALTO). Si la ventana se ha
redimensionado, la región se escala proporcionalmente.
"""

from typing import Tuple

import mss
from PIL import Image

Region = Tuple[int, int, int, int]  # (x, y, ancho, alto)
Rect = Tuple[int, int, int, int]  # (left, top, right, bottom)


def _scale_region(
    region: Region, ref_w: int, ref_h: int, cur_w: int, cur_h: int
) -> Region:
    """Escala una región del tamaño de referencia al tamaño actual de la ventana."""
    if ref_w and ref_h and (ref_w, ref_h) != (cur_w, cur_h):
        fx = cur_w / ref_w
        fy = cur_h / ref_h
        x, y, w, h = region
        return (round(x * fx), round(y * fy), round(w * fx), round(h * fy))
    return region


def _grab(left: int, top: int, width: int, height: int) -> Image.Image:
    bbox = {
        "left": int(left),
        "top": int(top),
        "width": max(1, int(width)),
        "height": max(1, int(height)),
    }
    with mss.mss() as sct:
        shot = sct.grab(bbox)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def capture_region(
    client_rect: Rect, region: Region, ref_size: Tuple[int, int]
) -> Image.Image:
    """Captura una región concreta del área de cliente de una ventana.

    Args:
        client_rect: (left, top, right, bottom) del área de cliente en pantalla.
        region: (x, y, ancho, alto) de la región, relativo al área de cliente.
        ref_size: (ref_ancho, ref_alto) del cliente cuando se definió la región.
    """
    cl, ct, cr, cb = client_rect
    cur_w, cur_h = cr - cl, cb - ct
    x, y, w, h = _scale_region(region, ref_size[0], ref_size[1], cur_w, cur_h)
    return _grab(cl + x, ct + y, w, h)


def capture_client_area(client_rect: Rect) -> Image.Image:
    """Captura completa del área de cliente (la usa la herramienta de marcado)."""
    cl, ct, cr, cb = client_rect
    return _grab(cl, ct, cr - cl, cb - ct)
