"""Ventana del Parte de Trabajo Diario.

Dos pestañas bajo la misma cabecera:
  - «Calendario»: vista diaria por horas (estilo Outlook) con la actividad
    y las empresas; vista principal.
  - «Detalle»: tabla editable de segmentos + tiempo por aplicación (AW).
"""

import sys
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from ..aw_reader import app_usage
from ..config import load_config
from ..db import WorkAuditDB, default_user
from .day_calendar import DayCalendarWidget
from .style import STYLESHEET, HeaderBand

DIAS = [
    "lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo",
]
MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
    "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def fecha_larga(d: date) -> str:
    return f"{DIAS[d.weekday()]}, {d.day} de {MESES[d.month - 1]} de {d.year}"


def format_seconds(total: float) -> str:
    """Segundos -> 'HH:MM:SS'."""
    total = int(total)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _parse(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def segment_seconds(seg: Dict[str, Any]) -> float:
    """Duración de un segmento; si está abierto, hasta el momento actual."""
    inicio = _parse(seg["HORAINICIO"])
    if inicio is None:
        return 0.0
    fin = _parse(seg["HORAFIN"]) or datetime.now(inicio.tzinfo)
    return max(0.0, (fin - inicio).total_seconds())


def _clear_layout(layout: QtWidgets.QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


class SegmentEditDialog(QtWidgets.QDialog):
    """Edición manual de la empresa/información de un segmento."""

    def __init__(self, parent, db: WorkAuditDB, seg: Dict[str, Any]) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Editar segmento #{seg['id']}")
        self.setMinimumWidth(420)
        self.seg = seg
        form = QtWidgets.QFormLayout(self)
        form.setSpacing(10)
        form.setContentsMargins(18, 18, 18, 18)

        self.empresa = QtWidgets.QComboBox()
        self.empresa.setEditable(True)
        self.empresa.addItem("", "")
        for emp in db.all_empresas():
            etiqueta = f"{emp['CODEMPRESA']} · {emp['NOMEMPRESA'] or ''}".strip()
            self.empresa.addItem(etiqueta, emp["CODEMPRESA"])
        actual = seg.get("CODEMPRESA") or ""
        idx = self.empresa.findData(actual)
        if idx >= 0:
            self.empresa.setCurrentIndex(idx)
        elif actual:
            self.empresa.setCurrentText(actual)

        self.informacion = QtWidgets.QPlainTextEdit(seg.get("INFORMACION") or "")
        self.informacion.setMaximumHeight(90)

        info = QtWidgets.QLabel(
            f"{seg['APLICACION']}  ·  "
            f"{(seg.get('TIPO') or 'app')}"
        )
        info.setObjectName("hintLabel")

        form.addRow("Actividad:", info)
        form.addRow("Empresa:", self.empresa)
        form.addRow("Información:", self.informacion)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
        ).setObjectName("primary")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def codempresa(self) -> Optional[str]:
        data = self.empresa.currentData()
        if data:
            return str(data)
        text = self.empresa.currentText().strip()
        return text.split("·")[0].strip() or None

    def informacion_text(self) -> str:
        return self.informacion.toPlainText().strip()


class EventImportDialog(QtWidgets.QDialog):
    """Importa una cita del calendario al parte como tiempo de reunión."""

    def __init__(self, parent, db: WorkAuditDB, evt: Dict[str, Any]) -> None:
        super().__init__(parent)
        ya_importada = evt.get("PARTE_ID") is not None
        self.setWindowTitle(
            "Actualizar cita importada" if ya_importada
            else "Importar cita al parte"
        )
        self.setMinimumWidth(440)
        form = QtWidgets.QFormLayout(self)
        form.setSpacing(10)
        form.setContentsMargins(18, 18, 18, 18)

        asunto = QtWidgets.QLabel(evt.get("ASUNTO") or "(reunión)")
        asunto.setWordWrap(True)
        asunto.setObjectName("hintLabel")

        ini = _parse(evt["INICIO"])
        fin = _parse(evt["FIN"])
        horario = QtWidgets.QLabel(
            f"{ini.strftime('%H:%M') if ini else '?'} – "
            f"{fin.strftime('%H:%M') if fin else '?'}"
        )

        self.empresa = QtWidgets.QComboBox()
        self.empresa.setEditable(True)
        self.empresa.addItem("", "")
        for emp in db.all_empresas():
            etiqueta = f"{emp['CODEMPRESA']} · {emp['NOMEMPRESA'] or ''}".strip()
            self.empresa.addItem(etiqueta, emp["CODEMPRESA"])
        actual = evt.get("CODEMPRESA") or ""
        idx = self.empresa.findData(actual)
        if idx >= 0:
            self.empresa.setCurrentIndex(idx)
        elif actual:
            self.empresa.setCurrentText(actual)

        form.addRow("Asunto:", asunto)
        form.addRow("Horario:", horario)
        form.addRow("Empresa:", self.empresa)

        nota = QtWidgets.QLabel(
            "La cita se actualizará en el parte." if ya_importada
            else "La cita se añadirá al parte como tiempo de reunión."
        )
        nota.setObjectName("cardHint")
        form.addRow("", nota)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        ok_btn.setObjectName("primary")
        ok_btn.setText("Importar al parte")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def codempresa(self) -> Optional[str]:
        data = self.empresa.currentData()
        if data:
            return str(data)
        return self.empresa.currentText().split("·")[0].strip() or None


class DailyReportWindow(QtWidgets.QWidget):
    """Ventana principal del parte diario."""

    def __init__(self, db: Optional[WorkAuditDB] = None) -> None:
        super().__init__()
        self.db = db or WorkAuditDB()
        self.cfg = load_config()
        self.usuario = self.cfg.get("usuario") or default_user()
        self.setWindowTitle("work-audit · Parte de Trabajo Diario")
        self.resize(1040, 760)
        self.setStyleSheet(STYLESHEET)
        self._segmentos: List[Dict[str, Any]] = []
        self._build_ui()
        self.refresh()

    # -- construcción de la interfaz ---------------------------------------

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.header = HeaderBand("Parte de Trabajo Diario")
        root.addWidget(self.header)
        root.addWidget(self._build_toolbar())

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.addTab(self._build_calendar_tab(), "Calendario")
        self.tabs.addTab(self._build_detail_tab(), "Detalle")
        root.addWidget(self.tabs, 1)

        root.addWidget(self._build_status_bar())

    def _build_toolbar(self) -> QtWidgets.QWidget:
        bar = QtWidgets.QFrame()
        bar.setObjectName("toolbar")
        bar.setFixedHeight(54)
        layout = QtWidgets.QHBoxLayout(bar)
        layout.setContentsMargins(18, 8, 18, 8)
        layout.setSpacing(8)

        layout.addWidget(QtWidgets.QLabel("📅  Fecha:"))
        self.date_edit = QtWidgets.QDateEdit(QtCore.QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.date_edit.dateChanged.connect(self.refresh)
        layout.addWidget(self.date_edit)

        today_btn = QtWidgets.QPushButton("Hoy")
        today_btn.clicked.connect(
            lambda: self.date_edit.setDate(QtCore.QDate.currentDate())
        )
        layout.addWidget(today_btn)
        layout.addStretch(1)

        refresh_btn = QtWidgets.QPushButton("↻  Actualizar")
        refresh_btn.setObjectName("primary")
        refresh_btn.clicked.connect(self.refresh)
        layout.addWidget(refresh_btn)
        return bar

    def _build_calendar_tab(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        self.chips_container = QtWidgets.QWidget()
        self.chips_layout = QtWidgets.QHBoxLayout(self.chips_container)
        self.chips_layout.setContentsMargins(0, 0, 0, 0)
        self.chips_layout.setSpacing(8)
        layout.addWidget(self.chips_container)

        self.calendar = DayCalendarWidget(self.db)
        self.calendar.segmentClicked.connect(self._do_edit)
        self.calendar.eventClicked.connect(self._import_event)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.calendar)
        scroll.setStyleSheet(
            "QScrollArea { border: 1px solid #EDEBE9; border-radius: 6px; }"
        )
        layout.addWidget(scroll, 1)
        return tab

    def _build_detail_tab(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)
        layout.addWidget(self._build_parte_card(), 1)
        layout.addWidget(self._build_usage_card())
        return tab

    def _make_card(self, titulo: str, hint: str = ""):
        card = QtWidgets.QFrame()
        card.setObjectName("card")
        outer = QtWidgets.QVBoxLayout(card)
        outer.setContentsMargins(18, 14, 18, 16)
        outer.setSpacing(10)
        cabecera = QtWidgets.QHBoxLayout()
        titulo_lbl = QtWidgets.QLabel(titulo)
        titulo_lbl.setObjectName("cardTitle")
        cabecera.addWidget(titulo_lbl)
        cabecera.addStretch(1)
        if hint:
            hint_lbl = QtWidgets.QLabel(hint)
            hint_lbl.setObjectName("cardHint")
            cabecera.addWidget(hint_lbl)
        outer.addLayout(cabecera)
        return card, outer

    def _style_table(self, table: QtWidgets.QTableWidget) -> None:
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(30)
        table.setSelectionBehavior(
            QtWidgets.QTableWidget.SelectionBehavior.SelectRows
        )
        table.setEditTriggers(QtWidgets.QTableWidget.EditTrigger.NoEditTriggers)
        table.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

    def _build_usage_card(self) -> QtWidgets.QWidget:
        card, layout = self._make_card(
            "Tiempo por aplicación", "Datos de ActivityWatch"
        )
        self.usage_table = QtWidgets.QTableWidget(0, 2)
        self.usage_table.setHorizontalHeaderLabels(["Aplicación", "Tiempo"])
        self._style_table(self.usage_table)
        header = self.usage_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        self.usage_table.setMaximumHeight(200)
        layout.addWidget(self.usage_table)
        return card

    def _build_parte_card(self) -> QtWidgets.QWidget:
        card, layout = self._make_card(
            "Parte detallado por empresa", "Doble clic en una fila para corregir"
        )
        self.parte_table = QtWidgets.QTableWidget(0, 7)
        self.parte_table.setHorizontalHeaderLabels(
            ["Empresa", "Actividad", "Inicio", "Fin", "Duración",
             "Información", "Sinc."]
        )
        self._style_table(self.parte_table)
        header = self.parte_table.horizontalHeader()
        for col in (0, 1, 2, 3, 4, 6):
            header.setSectionResizeMode(
                col, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
            )
        header.setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.parte_table.cellDoubleClicked.connect(self._edit_row)
        layout.addWidget(self.parte_table, 1)
        return card

    def _build_status_bar(self) -> QtWidgets.QWidget:
        bar = QtWidgets.QFrame()
        bar.setObjectName("statusBar")
        bar.setFixedHeight(28)
        layout = QtWidgets.QHBoxLayout(bar)
        layout.setContentsMargins(18, 0, 18, 0)
        self.status = QtWidgets.QLabel()
        layout.addWidget(self.status)
        layout.addStretch(1)
        return bar

    # -- datos --------------------------------------------------------------

    def _selected_date(self) -> date:
        qd = self.date_edit.date()
        return date(qd.year(), qd.month(), qd.day())

    def refresh(self) -> None:
        fecha = self._selected_date()
        self.header.set_subtitle(f"{self.usuario}  ·  {fecha_larga(fecha)}")

        self._segmentos = self.db.parte_del_dia(self.usuario, fecha.isoformat())

        # Sincronizar el calendario del origen configurado.
        source = self.cfg.get("calendar_source", "outlook")
        if source in ("outlook", "google"):
            try:
                if source == "outlook":
                    from ..outlook_calendar import sync_calendar
                else:
                    from ..google_calendar import sync_calendar
                sync_calendar(self.db, fecha, self.usuario)
            except Exception:  # noqa: BLE001
                pass
        eventos = self.db.eventos_del_dia(self.usuario, fecha.isoformat())

        self.calendar.set_data(self._segmentos, eventos, fecha.isoformat())
        self._fill_table()
        self._render_chips()
        self._load_usage(fecha)

    def _load_usage(self, fecha: date) -> None:
        filas = app_usage(fecha)
        self.usage_table.setRowCount(len(filas))
        for row, item in enumerate(filas):
            app_item = QtWidgets.QTableWidgetItem("  " + item["app"])
            tiempo_item = QtWidgets.QTableWidgetItem(
                format_seconds(item["segundos"]) + "  "
            )
            tiempo_item.setTextAlignment(
                QtCore.Qt.AlignmentFlag.AlignRight
                | QtCore.Qt.AlignmentFlag.AlignVCenter
            )
            self.usage_table.setItem(row, 0, app_item)
            self.usage_table.setItem(row, 1, tiempo_item)

    def _fill_table(self) -> None:
        self.parte_table.setRowCount(len(self._segmentos))
        muted = QtGui.QColor("#8A8886")
        for row, seg in enumerate(self._segmentos):
            cod = seg.get("CODEMPRESA") or ""
            emp = self.db.get_empresa(cod) if cod else None
            sin_asignar = not cod
            empresa_txt = (
                f"{cod} · {emp['NOMEMPRESA']}" if emp and emp.get("NOMEMPRESA")
                else (cod or "(sin asignar)")
            )
            inicio = _parse(seg["HORAINICIO"])
            fin = _parse(seg["HORAFIN"])
            actividad = seg["APLICACION"]
            if seg.get("TIPO") == "reunion":
                actividad = "📅 " + actividad
            valores = [
                empresa_txt,
                actividad,
                inicio.strftime("%H:%M:%S") if inicio else "",
                fin.strftime("%H:%M:%S") if fin else "en curso",
                format_seconds(segment_seconds(seg)),
                seg.get("INFORMACION") or "",
                "Sí" if seg["SINCRONIZADO"] else "No",
            ]
            for col, val in enumerate(valores):
                cell = QtWidgets.QTableWidgetItem(str(val))
                if col in (2, 3, 4, 6):
                    cell.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                if col == 0 and sin_asignar:
                    cell.setForeground(muted)
                if col == 6:
                    cell.setForeground(
                        QtGui.QColor("#107C10")
                        if seg["SINCRONIZADO"] else muted
                    )
                self.parte_table.setItem(row, col, cell)

    def _render_chips(self) -> None:
        _clear_layout(self.chips_layout)
        por_empresa: Dict[str, float] = defaultdict(float)
        for seg in self._segmentos:
            cod = seg.get("CODEMPRESA") or ""
            emp = self.db.get_empresa(cod) if cod else None
            etq = (
                f"{cod} · {emp['NOMEMPRESA']}" if emp and emp.get("NOMEMPRESA")
                else (cod or "(sin asignar)")
            )
            por_empresa[etq] += segment_seconds(seg)

        total_lbl = QtWidgets.QLabel("Total por empresa:")
        total_lbl.setObjectName("hintLabel")
        self.chips_layout.addWidget(total_lbl)
        if not por_empresa:
            vacio = QtWidgets.QLabel("Sin actividad registrada")
            vacio.setObjectName("chipMuted")
            self.chips_layout.addWidget(vacio)
        else:
            for empresa, secs in sorted(
                por_empresa.items(), key=lambda kv: kv[1], reverse=True
            ):
                chip = QtWidgets.QLabel(f"{empresa}  ·  {format_seconds(secs)}")
                chip.setObjectName(
                    "chipMuted" if empresa == "(sin asignar)" else "chip"
                )
                self.chips_layout.addWidget(chip)
        self.chips_layout.addStretch(1)
        n = len(self._segmentos)
        self.status.setText(f"{n} segmento(s) de actividad en el día.")

    # -- edición ------------------------------------------------------------

    def _edit_row(self, row: int, _col: int) -> None:
        if 0 <= row < len(self._segmentos):
            self._do_edit(self._segmentos[row])

    def _do_edit(self, seg: Dict[str, Any]) -> None:
        dlg = SegmentEditDialog(self, self.db, seg)
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        self.db.update_segment(
            seg["id"], dlg.codempresa(), dlg.informacion_text()
        )
        self.refresh()

    def _import_event(self, evt: Dict[str, Any]) -> None:
        """Importa (o actualiza) una cita del calendario como segmento de
        reunión en el parte de trabajo."""
        dlg = EventImportDialog(self, self.db, evt)
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        cod = dlg.codempresa()

        # Si ya estaba importada, sustituir su segmento anterior.
        if evt.get("PARTE_ID"):
            self.db.delete_segment(evt["PARTE_ID"])

        asunto = evt.get("ASUNTO") or "Reunión"
        seg_id = self.db.open_segment(
            usuario=self.usuario,
            aplicacion=asunto,
            codempresa=cod,
            informacion=evt.get("ORGANIZADOR") or "",
            tipo="reunion",
            horainicio=evt["INICIO"],
        )
        self.db.close_segment(seg_id, evt.get("FIN"))
        self.db.set_evento_parte(evt["id"], seg_id, cod)
        self.refresh()


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    window = DailyReportWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
