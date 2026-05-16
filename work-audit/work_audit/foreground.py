"""Detección de la ventana en primer plano (Windows).

Sondea la ventana activa con la API Win32 (pywin32), igual que hace
aw-watcher-window, y devuelve el proceso, el título y la geometría del
área de cliente para poder capturar regiones.
"""

import os
from dataclasses import dataclass
from typing import Optional, Tuple

try:
    import win32api
    import win32con
    import win32gui
    import win32process

    _WIN32 = True
except ImportError:  # plataforma no Windows o pywin32 ausente
    _WIN32 = False


Rect = Tuple[int, int, int, int]


@dataclass
class WindowInfo:
    """Información de una ventana en primer plano."""

    hwnd: int
    app: str  # nombre de proceso en minúsculas, p.ej. "sage.exe"
    title: str
    exe_path: str
    rect: Rect  # ventana completa (left, top, right, bottom) en pantalla
    client_rect: Rect  # área de cliente (left, top, right, bottom) en pantalla

    @property
    def client_size(self) -> Tuple[int, int]:
        l, t, r, b = self.client_rect
        return (r - l, b - t)


def _process_path(hwnd: int) -> str:
    """Ruta del ejecutable propietario de la ventana."""
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        handle = win32api.OpenProcess(
            win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ,
            False,
            pid,
        )
        try:
            return win32process.GetModuleFileNameEx(handle, 0)
        finally:
            win32api.CloseHandle(handle)
    except Exception:
        return ""


def get_foreground_window() -> Optional[WindowInfo]:
    """Devuelve la ventana en primer plano, o None si no se puede determinar."""
    if not _WIN32:
        return None

    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return None

    try:
        title = win32gui.GetWindowText(hwnd)
        rect = win32gui.GetWindowRect(hwnd)

        # Área de cliente -> coordenadas de pantalla
        cl, ct, cr, cb = win32gui.GetClientRect(hwnd)
        sx, sy = win32gui.ClientToScreen(hwnd, (cl, ct))
        ex, ey = win32gui.ClientToScreen(hwnd, (cr, cb))
        client_rect: Rect = (sx, sy, ex, ey)
    except Exception:
        return None

    exe_path = _process_path(hwnd)
    app = os.path.basename(exe_path).lower() if exe_path else ""

    return WindowInfo(
        hwnd=hwnd,
        app=app,
        title=title,
        exe_path=exe_path,
        rect=rect,
        client_rect=client_rect,
    )
