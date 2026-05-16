"""Icono de bandeja del sistema para work-audit.

Da acceso al parte diario, a la configuración y al marcado de regiones,
y permite cerrar la aplicación.
"""

from typing import Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from ..db import WorkAuditDB
from .config_window import ConfigWindow
from .daily_report import DailyReportWindow
from .region_trainer import RegionTrainer

# El acceso a Biloop vive ahora en Configuración → Empresas; el menú de la
# bandeja ya no abre ningún flujo de Biloop propio.


def _build_icon() -> QtGui.QIcon:
    """Genera un icono sencillo (no se depende de un archivo externo)."""
    pixmap = QtGui.QPixmap(64, 64)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    painter.setBrush(QtGui.QColor("#2962ff"))
    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    painter.drawEllipse(4, 4, 56, 56)
    painter.setPen(QtGui.QColor("white"))
    font = painter.font()
    font.setBold(True)
    font.setPointSize(26)
    painter.setFont(font)
    painter.drawText(
        pixmap.rect(), QtCore.Qt.AlignmentFlag.AlignCenter, "W"
    )
    painter.end()
    return QtGui.QIcon(pixmap)


class WorkAuditTray(QtWidgets.QSystemTrayIcon):
    """Icono de bandeja y menú de la aplicación."""

    def __init__(self, db: WorkAuditDB, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(_build_icon(), parent)
        self.db = db
        self.setToolTip("work-audit · Auditoría de trabajos")

        # Referencias persistentes a las ventanas (evita que se recolecten)
        self._report: Optional[DailyReportWindow] = None
        self._config: Optional[ConfigWindow] = None
        self._trainer: Optional[RegionTrainer] = None

        menu = QtWidgets.QMenu()
        menu.addAction("Parte diario", self.show_report)
        menu.addAction("Configuración", self.show_config)
        menu.addAction("Marcar regiones", self.show_trainer)
        menu.addSeparator()
        menu.addAction("Salir", self._quit)
        self.setContextMenu(menu)

        self.activated.connect(self._on_activated)

    def _on_activated(self, reason: QtWidgets.QSystemTrayIcon.ActivationReason) -> None:
        if reason == QtWidgets.QSystemTrayIcon.ActivationReason.Trigger:
            self.show_report()

    def show_report(self) -> None:
        if self._report is None:
            self._report = DailyReportWindow(self.db)
        else:
            self._report.refresh()
        self._report.show()
        self._report.raise_()
        self._report.activateWindow()

    def show_config(self) -> None:
        if self._config is None:
            self._config = ConfigWindow(self.db)
        self._config.show()
        self._config.raise_()
        self._config.activateWindow()

    def show_trainer(self) -> None:
        self._trainer = RegionTrainer(self.db)
        self._trainer.show()
        self._trainer.raise_()
        self._trainer.activateWindow()

    def _quit(self) -> None:
        QtWidgets.QApplication.instance().quit()
