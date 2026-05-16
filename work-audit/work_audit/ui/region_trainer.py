"""Herramienta de marcado ("entrenamiento") de regiones de pantalla.

Permite capturar la ventana de una aplicación, dibujar rectángulos sobre
las zonas donde aparece la información de la empresa, asignarles un nombre
y un tipo, y guardarlas en APLICACIONES_CAPTURAS. Estas definiciones son
comunes a todos los usuarios y se exportan al seed para distribuirlas.

Diseño con estética Microsoft Outlook / Fluent.
"""

import sys
from typing import Any, Dict, List, Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from ..capture import capture_client_area
from ..db import WorkAuditDB
from ..foreground import get_foreground_window
from ..ocr import ocr_image
from ..seed import export_seed
from .style import STYLESHEET, HeaderBand

TIPOS = ["codigorelacion", "codempresa", "nomempresa"]


def _pil_to_qpixmap(img) -> QtGui.QPixmap:
    rgba = img.convert("RGBA")
    qimg = QtGui.QImage(
        rgba.tobytes("raw", "RGBA"),
        rgba.width,
        rgba.height,
        QtGui.QImage.Format.Format_RGBA8888,
    )
    return QtGui.QPixmap.fromImage(qimg.copy())


class ScreenshotCanvas(QtWidgets.QLabel):
    """Lienzo que muestra la captura y permite dibujar regiones con el ratón."""

    regionDrawn = QtCore.pyqtSignal(QtCore.QRect)

    def __init__(self) -> None:
        super().__init__()
        self.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignLeft
        )
        self.setText("  La captura de la aplicación aparecerá aquí.")
        self.setStyleSheet("color: #8A8886; background: #FFFFFF;")
        self._origin: Optional[QtCore.QPoint] = None
        self._rubber = QtWidgets.QRubberBand(
            QtWidgets.QRubberBand.Shape.Rectangle, self
        )
        self._regions: List[tuple] = []  # (QRect, nombre)

    def set_image(self, img) -> None:
        pixmap = _pil_to_qpixmap(img)
        self.setPixmap(pixmap)
        self.resize(pixmap.size())
        self._regions.clear()
        self.update()

    def mousePressEvent(self, ev: QtGui.QMouseEvent) -> None:
        if self.pixmap() is None or self.pixmap().isNull():
            return
        self._origin = ev.pos()
        self._rubber.setGeometry(QtCore.QRect(self._origin, QtCore.QSize()))
        self._rubber.show()

    def mouseMoveEvent(self, ev: QtGui.QMouseEvent) -> None:
        if self._origin is not None:
            self._rubber.setGeometry(
                QtCore.QRect(self._origin, ev.pos()).normalized()
            )

    def mouseReleaseEvent(self, ev: QtGui.QMouseEvent) -> None:
        if self._origin is None:
            return
        rect = QtCore.QRect(self._origin, ev.pos()).normalized()
        self._rubber.hide()
        self._origin = None
        if rect.width() > 3 and rect.height() > 3:
            self.regionDrawn.emit(rect)

    def add_region_overlay(self, rect: QtCore.QRect, nombre: str) -> None:
        self._regions.append((rect, nombre))
        self.update()

    def clear_overlays(self) -> None:
        self._regions.clear()
        self.update()

    def paintEvent(self, ev: QtGui.QPaintEvent) -> None:
        super().paintEvent(ev)
        if not self._regions:
            return
        painter = QtGui.QPainter(self)
        painter.setPen(QtGui.QPen(QtGui.QColor("#0F6CBD"), 2))
        for rect, nombre in self._regions:
            painter.drawRect(rect)
            painter.fillRect(
                QtCore.QRect(rect.topLeft(), QtCore.QSize(rect.width(), 16)),
                QtGui.QColor(15, 108, 189, 60),
            )
            painter.drawText(rect.topLeft() + QtCore.QPoint(3, 13), nombre)
        painter.end()


class RegionDialog(QtWidgets.QDialog):
    """Pide nombre, tipo y regex de una región recién dibujada."""

    def __init__(self, parent, ocr_preview: str) -> None:
        super().__init__(parent)
        self.setWindowTitle("Definir región")
        self.setMinimumWidth(400)
        form = QtWidgets.QFormLayout(self)
        form.setSpacing(10)
        form.setContentsMargins(18, 18, 18, 18)

        self.nombre = QtWidgets.QLineEdit()
        self.tipo = QtWidgets.QComboBox()
        self.tipo.addItems(TIPOS)
        self.regex = QtWidgets.QLineEdit()
        preview = QtWidgets.QLabel(ocr_preview or "(sin texto)")
        preview.setWordWrap(True)
        preview.setStyleSheet(
            "color: #0F6CBD; font-family: 'Consolas', monospace; "
            "background: #EFF6FC; border: 1px solid #C7E0F4; "
            "border-radius: 4px; padding: 6px;"
        )

        form.addRow("Nombre del campo:", self.nombre)
        form.addRow("Tipo:", self.tipo)
        form.addRow("Regex (opcional):", self.regex)
        form.addRow("OCR detectado:", preview)

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

    def values(self) -> Dict[str, str]:
        return {
            "nombre": self.nombre.text().strip(),
            "tipo": self.tipo.currentText(),
            "regex": self.regex.text().strip(),
        }


class RegionTrainer(QtWidgets.QWidget):
    """Ventana principal de la herramienta de marcado de regiones."""

    def __init__(self, db: Optional[WorkAuditDB] = None) -> None:
        super().__init__()
        self.db = db or WorkAuditDB()
        self.setWindowTitle("work-audit · Marcado de regiones")
        self.resize(1120, 780)
        self.setStyleSheet(STYLESHEET)

        self.screenshot = None  # imagen PIL capturada
        self.ref_size = (0, 0)  # tamaño del área de cliente al capturar
        self.pending: List[Dict[str, Any]] = []  # regiones a guardar

        self._build_ui()

    # -- construcción de la interfaz ---------------------------------------

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(
            HeaderBand(
                "Marcado de Regiones",
                "Define las zonas de pantalla donde aparece la empresa",
            )
        )

        content = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(content)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        # Barra superior
        top = QtWidgets.QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(QtWidgets.QLabel("Aplicación:"))
        self.app_edit = QtWidgets.QLineEdit()
        self.app_edit.setPlaceholderText("nombre_proceso.exe")
        top.addWidget(self.app_edit, 1)
        self.capture_btn = QtWidgets.QPushButton("📸  Capturar ventana activa (3 s)")
        self.capture_btn.setObjectName("primary")
        self.capture_btn.clicked.connect(self._start_capture)
        top.addWidget(self.capture_btn)
        layout.addLayout(top)

        self.status = QtWidgets.QLabel(
            "Abre la aplicación a auditar y pulsa «Capturar»: "
            "tendrás 3 s para activar su ventana."
        )
        self.status.setObjectName("hintLabel")
        layout.addWidget(self.status)

        # Lienzo de la captura, dentro de un área desplazable
        self.canvas = ScreenshotCanvas()
        self.canvas.regionDrawn.connect(self._on_region_drawn)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidget(self.canvas)
        scroll.setWidgetResizable(False)
        scroll.setStyleSheet(
            "QScrollArea { border: 1px solid #EDEBE9; border-radius: 6px; "
            "background: #FFFFFF; }"
        )
        layout.addWidget(scroll, 1)

        # Tabla de regiones definidas
        self.table = QtWidgets.QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Campo", "Tipo", "X", "Y", "Ancho", "Alto"]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(
            QtWidgets.QTableWidget.SelectionBehavior.SelectRows
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMaximumHeight(170)
        layout.addWidget(self.table)

        # Botones inferiores
        bottom = QtWidgets.QHBoxLayout()
        bottom.setSpacing(8)
        del_btn = QtWidgets.QPushButton("Eliminar región seleccionada")
        del_btn.clicked.connect(self._delete_selected)
        bottom.addWidget(del_btn)
        bottom.addStretch(1)
        seed_btn = QtWidgets.QPushButton("Exportar seed")
        seed_btn.clicked.connect(self._export_seed)
        bottom.addWidget(seed_btn)
        save_btn = QtWidgets.QPushButton("Guardar en base de datos")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self._save)
        bottom.addWidget(save_btn)
        layout.addLayout(bottom)

        root.addWidget(content, 1)

    # -- captura ------------------------------------------------------------

    def _start_capture(self) -> None:
        self.capture_btn.setEnabled(False)
        self._countdown = 3
        self.status.setText(f"Capturando en {self._countdown}...")
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick_capture)
        self._timer.start(1000)

    def _tick_capture(self) -> None:
        self._countdown -= 1
        if self._countdown > 0:
            self.status.setText(f"Capturando en {self._countdown}...")
            return
        self._timer.stop()
        self._do_capture()
        self.capture_btn.setEnabled(True)

    def _do_capture(self) -> None:
        win = get_foreground_window()
        if win is None:
            self.status.setText("No se pudo determinar la ventana activa.")
            return
        try:
            self.screenshot = capture_client_area(win.client_rect)
        except Exception as e:  # noqa: BLE001
            self.status.setText(f"Error capturando la pantalla: {e}")
            return
        self.ref_size = win.client_size
        if not self.app_edit.text().strip():
            self.app_edit.setText(win.app)
        self.canvas.set_image(self.screenshot)
        self.pending.clear()
        self.table.setRowCount(0)
        self.status.setText(
            f"Capturado «{win.app}» ({self.ref_size[0]}×{self.ref_size[1]}). "
            "Dibuja rectángulos sobre las zonas de empresa."
        )

    # -- regiones -----------------------------------------------------------

    def _on_region_drawn(self, rect: QtCore.QRect) -> None:
        if self.screenshot is None:
            return
        crop = self.screenshot.crop(
            (rect.x(), rect.y(), rect.x() + rect.width(), rect.y() + rect.height())
        )
        ocr_preview = ocr_image(crop)

        dlg = RegionDialog(self, ocr_preview)
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        vals = dlg.values()
        if not vals["nombre"]:
            QtWidgets.QMessageBox.warning(self, "work-audit", "El nombre es obligatorio.")
            return

        region = {
            "nombre": vals["nombre"],
            "tipo": vals["tipo"],
            "regex": vals["regex"] or None,
            "x": rect.x(),
            "y": rect.y(),
            "ancho": rect.width(),
            "alto": rect.height(),
        }
        self.pending.append(region)
        self.canvas.add_region_overlay(rect, vals["nombre"])
        self._add_table_row(region)

    def _add_table_row(self, region: Dict[str, Any]) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        for col, key in enumerate(["nombre", "tipo", "x", "y", "ancho", "alto"]):
            self.table.setItem(row, col, QtWidgets.QTableWidgetItem(str(region[key])))

    def _delete_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        self.table.removeRow(row)
        del self.pending[row]
        self._redraw_overlays()

    def _redraw_overlays(self) -> None:
        self.canvas.clear_overlays()
        for region in self.pending:
            rect = QtCore.QRect(
                region["x"], region["y"], region["ancho"], region["alto"]
            )
            self.canvas.add_region_overlay(rect, region["nombre"])

    # -- persistencia -------------------------------------------------------

    def _save(self) -> None:
        app = self.app_edit.text().strip().lower()
        if not app:
            QtWidgets.QMessageBox.warning(
                self, "work-audit", "Indica el nombre de la aplicación."
            )
            return
        if not self.pending:
            QtWidgets.QMessageBox.warning(
                self, "work-audit", "No hay regiones que guardar."
            )
            return

        self.db.upsert_aplicacion(app, ruta="")
        for region in self.pending:
            self.db.upsert_captura(
                aplicacion=app,
                nombre_campo=region["nombre"],
                tipo=region["tipo"],
                x=region["x"],
                y=region["y"],
                ancho=region["ancho"],
                alto=region["alto"],
                ref_ancho=self.ref_size[0],
                ref_alto=self.ref_size[1],
                regex=region["regex"],
            )
        QtWidgets.QMessageBox.information(
            self,
            "work-audit",
            f"Guardadas {len(self.pending)} regiones para «{app}».",
        )

    def _export_seed(self) -> None:
        path = export_seed(self.db)
        QtWidgets.QMessageBox.information(
            self, "work-audit", f"Seed exportado a:\n{path}"
        )


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    window = RegionTrainer()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
