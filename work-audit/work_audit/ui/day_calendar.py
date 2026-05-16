"""Vista de calendario diario por horas (estilo día de Outlook).

Pinta los segmentos de PARTE_TRABAJO como bloques posicionados por hora y
coloreados por empresa, además de los eventos del calendario de Outlook en
un carril lateral.

Cuando varios bloques se solapan visualmente se reparten en columnas,
agrupadas por (aplicación, empresa). La altura de cada hora se adapta al
número de combinaciones distintas de aplicación/empresa del día.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from PyQt6 import QtCore, QtGui, QtWidgets

from ..db import WorkAuditDB

# Paleta determinista de colores por empresa.
_PALETTE = [
    "#0F6CBD", "#107C10", "#C19C00", "#8764B8",
    "#CA5010", "#038387", "#A4262C", "#4F6BED",
]


def company_color(code: Optional[str]) -> QtGui.QColor:
    """Color estable para una empresa (gris si no hay empresa)."""
    if not code:
        return QtGui.QColor("#9E9E9E")
    idx = sum(ord(ch) for ch in str(code)) % len(_PALETTE)
    return QtGui.QColor(_PALETTE[idx])


def _to_local(ts: Optional[str]) -> Optional[datetime]:
    """Convierte un timestamp ISO (UTC) a datetime local."""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return None
    return dt.astimezone()


def _hour_of(dt: datetime) -> float:
    return dt.hour + dt.minute / 60.0 + dt.second / 3600.0


class DayCalendarWidget(QtWidgets.QWidget):
    """Lienzo del calendario diario. Se coloca dentro de un QScrollArea."""

    segmentClicked = QtCore.pyqtSignal(dict)
    eventClicked = QtCore.pyqtSignal(dict)

    GUTTER = 58            # ancho de la columna de horas
    TOP = 10
    EVENT_LANE = 150       # ancho del carril de eventos de calendario
    MIN_BLOCK = 26         # altura mínima de un bloque
    HOUR_BASE = 68         # altura base de una hora
    HOUR_MAX = 260         # altura máxima de una hora

    def __init__(self, db: WorkAuditDB) -> None:
        super().__init__()
        self.db = db
        self._segments: List[Dict[str, Any]] = []
        self._events: List[Dict[str, Any]] = []
        self._fecha: Optional[str] = None
        self._hour_start = 8
        self._hour_end = 20
        self._hour_height = self.HOUR_BASE
        self._items: List[Dict[str, Any]] = []   # bloques con su disposición
        self._blocks: List[tuple] = []           # (QRect, segmento)
        self._event_blocks: List[tuple] = []      # (QRect, evento)
        self._empresa_cache: Dict[str, str] = {}
        self.setMouseTracking(True)
        self.setMinimumWidth(560)

    # -- datos --------------------------------------------------------------

    def set_data(
        self,
        segments: List[Dict[str, Any]],
        events: Optional[List[Dict[str, Any]]] = None,
        fecha: Optional[str] = None,
    ) -> None:
        self._segments = segments
        self._events = events or []
        self._fecha = fecha
        self._empresa_cache.clear()

        # Rango horario: 8–20 ampliado para cubrir toda la actividad.
        h_min, h_max = 8.0, 20.0
        for seg in segments:
            ini = _to_local(seg["HORAINICIO"])
            fin = _to_local(seg["HORAFIN"]) or datetime.now().astimezone()
            if ini:
                h_min = min(h_min, _hour_of(ini))
                h_max = max(h_max, _hour_of(fin))
        for ev in self._events:
            ini = _to_local(ev["INICIO"])
            fin = _to_local(ev["FIN"]) or ini
            if ini:
                h_min = min(h_min, _hour_of(ini))
            if fin:
                h_max = max(h_max, _hour_of(fin))
        self._hour_start = int(h_min)
        self._hour_end = min(24, int(h_max) + 1)

        # Altura de hora adaptada al nº de combinaciones aplicación/empresa.
        combinaciones = {
            (s["APLICACION"], s.get("CODEMPRESA")) for s in segments
        }
        self._hour_height = min(
            self.HOUR_MAX, self.HOUR_BASE + len(combinaciones) * 18
        )

        self._layout_segments()
        total = self.TOP * 2 + (self._hour_end - self._hour_start) * self._hour_height
        self.setMinimumHeight(total)
        self.update()

    # -- disposición de bloques --------------------------------------------

    def _layout_segments(self) -> None:
        """Calcula y0/y1, columna y nº de columnas de cada segmento.

        Los bloques cuyos rectángulos se solapan verticalmente se reparten en
        columnas; se reutiliza la columna de la misma (aplicación, empresa)
        siempre que sea posible.
        """
        items: List[Dict[str, Any]] = []
        for seg in self._segments:
            ini = _to_local(seg["HORAINICIO"])
            fin = _to_local(seg["HORAFIN"]) or datetime.now().astimezone()
            if ini is None:
                continue
            y0 = self._y(max(self._hour_start, _hour_of(ini)))
            y1 = self._y(min(self._hour_end, _hour_of(fin)))
            y1 = max(y1, y0 + self.MIN_BLOCK)
            items.append({
                "seg": seg, "y0": y0, "y1": y1,
                "key": (seg["APLICACION"], seg.get("CODEMPRESA")),
                "col": 0, "ncols": 1,
            })
        items.sort(key=lambda it: it["y0"])

        # Agrupar en racimos de bloques que se solapan y asignar columnas.
        i = 0
        while i < len(items):
            cluster = [items[i]]
            cluster_end = items[i]["y1"]
            j = i + 1
            while j < len(items) and items[j]["y0"] < cluster_end:
                cluster.append(items[j])
                cluster_end = max(cluster_end, items[j]["y1"])
                j += 1
            self._assign_columns(cluster)
            i = j

        self._items = items

    @staticmethod
    def _assign_columns(cluster: List[Dict[str, Any]]) -> None:
        columns: List[Dict[str, Any]] = []  # {"end": y1, "key": key}
        for it in cluster:
            ci = None
            # Preferir una columna libre con la misma (app, empresa).
            for k, col in enumerate(columns):
                if col["end"] <= it["y0"] and col["key"] == it["key"]:
                    ci = k
                    break
            # Si no, la primera columna libre.
            if ci is None:
                for k, col in enumerate(columns):
                    if col["end"] <= it["y0"]:
                        ci = k
                        break
            if ci is None:
                columns.append({"end": it["y1"], "key": it["key"]})
                ci = len(columns) - 1
            else:
                columns[ci]["end"] = it["y1"]
                columns[ci]["key"] = it["key"]
            it["col"] = ci
        ncols = max(1, len(columns))
        for it in cluster:
            it["ncols"] = ncols

    # -- geometría ----------------------------------------------------------

    def _y(self, hour: float) -> int:
        return int(self.TOP + (hour - self._hour_start) * self._hour_height)

    def _app_lane(self) -> Tuple[int, int]:
        """(x_inicio, ancho) del carril de aplicaciones."""
        x = self.GUTTER + 8
        w = self.width() - self.GUTTER - self.EVENT_LANE - 24
        return x, max(80, w)

    def _empresa_label(self, code: Optional[str]) -> str:
        if not code:
            return "(sin asignar)"
        if code not in self._empresa_cache:
            emp = self.db.get_empresa(code)
            self._empresa_cache[code] = (
                f"{code} · {emp['NOMEMPRESA']}" if emp and emp.get("NOMEMPRESA")
                else code
            )
        return self._empresa_cache[code]

    # -- pintado ------------------------------------------------------------

    def paintEvent(self, ev: QtGui.QPaintEvent) -> None:
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QtGui.QColor("#FFFFFF"))

        self._paint_grid(p)
        self._blocks = []
        for it in self._items:
            self._paint_segment(p, it)
        self._event_blocks = []
        for evt in self._events:
            self._paint_event(p, evt)
        self._paint_now_line(p)
        p.end()

    def _paint_grid(self, p: QtGui.QPainter) -> None:
        for h in range(self._hour_start, self._hour_end + 1):
            y = self._y(h)
            p.setPen(QtGui.QPen(QtGui.QColor("#EDEBE9")))
            p.drawLine(self.GUTTER, y, self.width(), y)
            if h < self._hour_end:
                p.setPen(QtGui.QPen(QtGui.QColor("#F3F2F1")))
                p.drawLine(self.GUTTER, y + self._hour_height // 2,
                           self.width(), y + self._hour_height // 2)
            p.setPen(QtGui.QColor("#8A8886"))
            p.drawText(
                QtCore.QRect(0, y - 9, self.GUTTER - 10, 18),
                QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter,
                f"{h:02d}:00",
            )

    def _paint_segment(self, p: QtGui.QPainter, it: Dict[str, Any]) -> None:
        seg = it["seg"]
        lane_x, lane_w = self._app_lane()
        col_w = lane_w / it["ncols"]
        x = int(lane_x + it["col"] * col_w)
        w = int(col_w) - 4
        rect = QtCore.QRect(x, it["y0"], max(60, w), it["y1"] - it["y0"])

        color = company_color(seg.get("CODEMPRESA"))
        es_reunion = seg.get("TIPO") == "reunion"

        fondo = QtGui.QColor(color)
        fondo.setAlpha(38)
        p.fillRect(rect, fondo)
        p.fillRect(QtCore.QRect(rect.x(), rect.y(), 4, rect.height()), color)
        p.setPen(QtGui.QPen(QtGui.QColor("#E1DFDD")))
        p.drawRect(rect)

        ini = _to_local(seg["HORAINICIO"])
        fin = _to_local(seg["HORAFIN"]) or datetime.now().astimezone()
        textrect = rect.adjusted(12, 4, -8, -4)
        p.setPen(QtGui.QColor("#201F1E"))
        font = p.font()
        font.setBold(True)
        p.setFont(font)
        titulo = ("📅 " if es_reunion else "") + seg["APLICACION"]
        p.drawText(
            textrect,
            QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignLeft,
            titulo,
        )
        if rect.height() > 38:
            font.setBold(False)
            p.setFont(font)
            p.setPen(QtGui.QColor("#605E5C"))
            detalle = (
                f"{self._empresa_label(seg.get('CODEMPRESA'))}    "
                f"{ini.strftime('%H:%M') if ini else ''}–{fin.strftime('%H:%M')}"
            )
            p.drawText(
                textrect.adjusted(0, 18, 0, 0),
                QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignLeft,
                detalle,
            )
        self._blocks.append((rect, seg))

    def _paint_event(self, p: QtGui.QPainter, evt: Dict[str, Any]) -> None:
        ini = _to_local(evt["INICIO"])
        fin = _to_local(evt["FIN"]) or ini
        if ini is None or fin is None:
            return
        y0 = self._y(max(self._hour_start, _hour_of(ini)))
        y1 = self._y(min(self._hour_end, _hour_of(fin)))
        rect = QtCore.QRect(
            self.width() - self.EVENT_LANE - 6, y0,
            self.EVENT_LANE, max(self.MIN_BLOCK, y1 - y0),
        )
        color = company_color(evt.get("CODEMPRESA"))
        importado = evt.get("PARTE_ID") is not None

        fondo = QtGui.QColor(color)
        fondo.setAlpha(46 if importado else 26)
        p.fillRect(rect, fondo)
        pen = QtGui.QPen(color)
        pen.setWidth(2 if importado else 1)
        if not importado:
            pen.setStyle(QtCore.Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawRect(rect)

        textrect = rect.adjusted(8, 4, -6, -4)
        p.setPen(QtGui.QColor("#201F1E"))
        font = p.font()
        font.setBold(True)
        p.setFont(font)
        prefijo = "✓ " if importado else "🗓 "
        p.drawText(
            textrect,
            QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignLeft,
            prefijo + (evt.get("ASUNTO") or "(reunión)"),
        )
        if rect.height() > 38:
            font.setBold(False)
            p.setFont(font)
            p.setPen(QtGui.QColor("#605E5C"))
            p.drawText(
                textrect.adjusted(0, 18, 0, 0),
                QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignLeft,
                self._empresa_label(evt.get("CODEMPRESA")),
            )
        self._event_blocks.append((rect, evt))

    def _paint_now_line(self, p: QtGui.QPainter) -> None:
        ahora = datetime.now().astimezone()
        if self._fecha and ahora.date().isoformat() != self._fecha:
            return
        h = _hour_of(ahora)
        if not (self._hour_start <= h <= self._hour_end):
            return
        y = self._y(h)
        p.setPen(QtGui.QPen(QtGui.QColor("#D13438"), 2))
        p.drawLine(self.GUTTER, y, self.width(), y)
        p.setBrush(QtGui.QColor("#D13438"))
        p.drawEllipse(QtCore.QPoint(self.GUTTER, y), 4, 4)

    # -- interacción --------------------------------------------------------

    def mousePressEvent(self, ev: QtGui.QMouseEvent) -> None:
        pos = ev.pos()
        for rect, seg in self._blocks:
            if rect.contains(pos):
                self.segmentClicked.emit(seg)
                return
        for rect, evt in self._event_blocks:
            if rect.contains(pos):
                self.eventClicked.emit(evt)
                return

    def mouseMoveEvent(self, ev: QtGui.QMouseEvent) -> None:
        pos = ev.pos()
        sobre = any(r.contains(pos) for r, _ in self._blocks + self._event_blocks)
        self.setCursor(
            QtCore.Qt.CursorShape.PointingHandCursor
            if sobre
            else QtCore.Qt.CursorShape.ArrowCursor
        )
