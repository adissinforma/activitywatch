"""Detección de inactividad del usuario en Windows.

Devuelve los segundos transcurridos desde la última entrada de teclado o
ratón, mediante la API Win32 GetLastInputInfo.
"""

import ctypes
from ctypes import wintypes


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def idle_seconds() -> float:
    """Segundos desde la última actividad de teclado/ratón.

    Devuelve 0.0 si no se puede determinar (p. ej. plataforma no Windows).
    """
    try:
        info = _LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(info)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return 0.0
        tick = ctypes.windll.kernel32.GetTickCount()
        # GetTickCount se reinicia cada ~49 días; max() evita valores negativos.
        return max(0.0, (tick - info.dwTime) / 1000.0)
    except Exception:
        return 0.0
