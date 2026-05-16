"""Estilo visual común del módulo work-audit (estética Microsoft Outlook / Fluent).

Define la hoja de estilo (QSS) compartida por todas las ventanas y el
componente de cabecera azul reutilizable.
"""

from PyQt6 import QtWidgets

# Paleta Fluent / Outlook
COLOR_PRIMARY = "#0F6CBD"
COLOR_PRIMARY_DARK = "#115EA3"
COLOR_BG = "#FAF9F8"
COLOR_TEXT = "#323130"

STYLESHEET = """
* { font-family: 'Segoe UI'; }
QWidget { background: #FAF9F8; color: #323130; font-size: 10pt; }

/* --- Cabecera azul --- */
#headerBand { background: #0F6CBD; }
#headerTitle { color: #FFFFFF; font-size: 18pt; font-weight: 600; }
#headerSub { color: #D2E4F6; font-size: 10pt; }

/* --- Barra de herramientas / tarjetas --- */
#toolbar { background: #FFFFFF; border-bottom: 1px solid #EDEBE9; }
#toolbar QLabel { color: #605E5C; }

#card {
    background: #FFFFFF;
    border: 1px solid #EDEBE9;
    border-radius: 8px;
}
#cardTitle { font-size: 11pt; font-weight: 600; color: #201F1E; }
#cardHint { color: #8A8886; font-size: 9pt; }

/* --- Tablas --- */
QTableWidget {
    background: #FFFFFF;
    border: 1px solid #EDEBE9;
    border-radius: 4px;
    gridline-color: transparent;
    alternate-background-color: #FBFAFA;
    selection-background-color: #CCE4F7;
    selection-color: #201F1E;
    outline: 0;
}
QTableWidget::item { padding: 5px 8px; border: none; }
QHeaderView::section {
    background: #F3F2F1;
    color: #605E5C;
    padding: 7px 8px;
    border: none;
    border-bottom: 1px solid #E1DFDD;
    font-weight: 600;
}
QTableCornerButton::section { background: #F3F2F1; border: none; }

/* --- Pestañas --- */
QTabWidget::pane {
    border: 1px solid #EDEBE9;
    border-radius: 6px;
    background: #FFFFFF;
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    color: #605E5C;
    padding: 8px 20px;
    border: none;
    border-bottom: 2px solid transparent;
    font-weight: 600;
}
QTabBar::tab:selected { color: #0F6CBD; border-bottom: 2px solid #0F6CBD; }
QTabBar::tab:hover:!selected { color: #323130; }

/* --- Botones --- */
QPushButton {
    background: #FFFFFF;
    border: 1px solid #C8C6C4;
    border-radius: 4px;
    padding: 6px 14px;
    color: #323130;
}
QPushButton:hover { background: #F3F2F1; }
QPushButton:pressed { background: #EDEBE9; }
QPushButton:disabled { color: #A19F9D; background: #F3F2F1; }

QPushButton#primary {
    background: #0F6CBD;
    border: 1px solid #0F6CBD;
    color: #FFFFFF;
    font-weight: 600;
}
QPushButton#primary:hover { background: #115EA3; border-color: #115EA3; }
QPushButton#primary:pressed { background: #0E4F86; }
QPushButton#primary:disabled { background: #92B5D1; border-color: #92B5D1; }

/* --- Campos de entrada --- */
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit {
    background: #FFFFFF;
    border: 1px solid #C8C6C4;
    border-radius: 4px;
    padding: 5px 8px;
    selection-background-color: #CCE4F7;
    selection-color: #201F1E;
}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus { border-color: #0F6CBD; }
QLineEdit:hover, QComboBox:hover, QSpinBox:hover,
QDoubleSpinBox:hover, QDateEdit:hover { border-color: #0F6CBD; }
QComboBox::drop-down, QDateEdit::drop-down { border: none; width: 22px; }
QDateEdit { min-width: 130px; }
QCheckBox { spacing: 8px; }

/* --- Chips de resumen --- */
QLabel#chip {
    background: #EFF6FC;
    color: #0F6CBD;
    border: 1px solid #C7E0F4;
    border-radius: 11px;
    padding: 4px 12px;
    font-weight: 600;
}
QLabel#chipMuted {
    background: #F3F2F1;
    color: #605E5C;
    border: 1px solid #E1DFDD;
    border-radius: 11px;
    padding: 4px 12px;
    font-weight: 600;
}

/* --- Varios --- */
#statusBar { background: #F3F2F1; color: #605E5C; border-top: 1px solid #E1DFDD; }
#hintLabel { color: #605E5C; }
QScrollArea { border: none; background: #FAF9F8; }
QGroupBox { border: none; }
QLabel { background: transparent; }
"""


class HeaderBand(QtWidgets.QFrame):
    """Banda de cabecera azul con título y subtítulo (estilo Outlook)."""

    def __init__(self, title: str, subtitle: str = "") -> None:
        super().__init__()
        self.setObjectName("headerBand")
        self.setFixedHeight(88)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(22, 0, 22, 0)
        layout.setSpacing(3)
        layout.addStretch(1)

        self._title = QtWidgets.QLabel(title)
        self._title.setObjectName("headerTitle")
        self._sub = QtWidgets.QLabel(subtitle)
        self._sub.setObjectName("headerSub")

        layout.addWidget(self._title)
        layout.addWidget(self._sub)
        layout.addStretch(1)

    def set_subtitle(self, text: str) -> None:
        self._sub.setText(text)
