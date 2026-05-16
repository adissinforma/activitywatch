"""Ventana de configuración del módulo work-audit.

Tres pestañas:
  - Aplicaciones: lista de aplicaciones (tabla APLICACIONES), su empresa por
    defecto y acceso al marcado de regiones.
  - Empresas: catálogo de empresas (alta manual, importación de Excel) y el
    panel «Acceso a Biloop» para traer las empresas autorizadas del portal.
  - Ajustes: parámetros del módulo (work-audit.toml).

Diseño con estética Microsoft Outlook / Fluent.
"""

import sys
from typing import Optional

from PyQt6 import QtCore, QtWidgets

from ..config import load_config, save_config
from ..credenciales import guardar_password, leer_password, olvidar_password
from ..db import WorkAuditDB
from .region_trainer import RegionTrainer
from .style import STYLESHEET, HeaderBand


def _style_table(table: QtWidgets.QTableWidget) -> None:
    """Aplica el aspecto Outlook a una tabla."""
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(30)
    table.setSelectionBehavior(
        QtWidgets.QTableWidget.SelectionBehavior.SelectRows
    )


def _fill_empresas_combo(combo: QtWidgets.QComboBox, db: WorkAuditDB) -> None:
    """Rellena un combo editable con las empresas conocidas."""
    combo.setEditable(True)
    combo.addItem("", "")
    for emp in db.all_empresas():
        etiqueta = f"{emp['CODEMPRESA']} · {emp['NOMEMPRESA'] or ''}".strip()
        combo.addItem(etiqueta, emp["CODEMPRESA"])


def _combo_codempresa(combo: QtWidgets.QComboBox) -> str:
    """Extrae el código de empresa de un combo (selección o texto libre)."""
    data = combo.currentData()
    if data:
        return str(data)
    return combo.currentText().split("·")[0].strip()


class AplicacionesTab(QtWidgets.QWidget):
    """Gestión de la lista de aplicaciones a auditar."""

    def __init__(self, db: WorkAuditDB) -> None:
        super().__init__()
        self.db = db
        self._trainer: Optional[RegionTrainer] = None
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        hint = QtWidgets.QLabel(
            "Aplicaciones con configuración propia. Las entrenables se marcan "
            "con «Marcar regiones»; para el resto puedes fijar aquí su empresa "
            "por defecto (código de empresa)."
        )
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.table = QtWidgets.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Aplicación", "Ruta", "Empresa por defecto", "Activa", "Regiones"]
        )
        _style_table(self.table)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        botones = QtWidgets.QHBoxLayout()
        botones.setSpacing(8)
        add_btn = QtWidgets.QPushButton("Añadir aplicación")
        add_btn.clicked.connect(self._add)
        del_btn = QtWidgets.QPushButton("Eliminar")
        del_btn.clicked.connect(self._delete)
        train_btn = QtWidgets.QPushButton("Marcar regiones…")
        train_btn.setObjectName("primary")
        train_btn.clicked.connect(self._open_trainer)
        botones.addWidget(add_btn)
        botones.addWidget(del_btn)
        botones.addStretch(1)
        botones.addWidget(train_btn)
        layout.addLayout(botones)

        self.refresh()

    def refresh(self) -> None:
        apps = self.db.list_aplicaciones()
        self.table.setRowCount(len(apps))
        for row, app in enumerate(apps):
            nombre = QtWidgets.QTableWidgetItem(app["APLICACION"])
            nombre.setFlags(nombre.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, nombre)
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(app["RUTA"] or ""))
            self.table.setItem(
                row, 2,
                QtWidgets.QTableWidgetItem(app.get("CODEMPRESA_DEFECTO") or ""),
            )

            check = QtWidgets.QTableWidgetItem()
            check.setFlags(
                QtCore.Qt.ItemFlag.ItemIsUserCheckable
                | QtCore.Qt.ItemFlag.ItemIsEnabled
            )
            check.setCheckState(
                QtCore.Qt.CheckState.Checked
                if app["activo"]
                else QtCore.Qt.CheckState.Unchecked
            )
            check.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, check)

            n_regiones = len(self.db.get_capturas(app["APLICACION"]))
            reg = QtWidgets.QTableWidgetItem(str(n_regiones))
            reg.setFlags(reg.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            reg.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 4, reg)

    def save(self) -> None:
        """Persiste ruta, empresa por defecto y estado activo de cada fila."""
        for row in range(self.table.rowCount()):
            aplicacion = self.table.item(row, 0).text()
            ruta = self.table.item(row, 1).text().strip()
            empresa = self.table.item(row, 2).text().strip()
            activo = (
                self.table.item(row, 3).checkState() == QtCore.Qt.CheckState.Checked
            )
            self.db.upsert_aplicacion(aplicacion, ruta, activo)
            self.db.set_aplicacion_activo(aplicacion, activo)
            self.db.set_aplicacion_empresa_defecto(aplicacion, empresa or None)

    def _add(self) -> None:
        nombre, ok = QtWidgets.QInputDialog.getText(
            self, "Añadir aplicación", "Nombre del proceso (p.ej. sage.exe):"
        )
        if not ok or not nombre.strip():
            return
        self.db.upsert_aplicacion(nombre.strip().lower(), ruta="")
        self.refresh()

    def _delete(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        aplicacion = self.table.item(row, 0).text()
        confirm = QtWidgets.QMessageBox.question(
            self,
            "work-audit",
            f"¿Eliminar «{aplicacion}» y sus regiones?",
        )
        if confirm == QtWidgets.QMessageBox.StandardButton.Yes:
            self.db.delete_aplicacion(aplicacion)
            self.refresh()

    def _open_trainer(self) -> None:
        self._trainer = RegionTrainer(self.db)
        row = self.table.currentRow()
        if row >= 0:
            self._trainer.app_edit.setText(self.table.item(row, 0).text())
        self._trainer.show()


class AjustesTab(QtWidgets.QWidget):
    """Edición de los parámetros de work-audit.toml."""

    def __init__(self, db: WorkAuditDB) -> None:
        super().__init__()
        self.db = db
        cfg = load_config()

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        form = QtWidgets.QFormLayout()
        self._form = form
        form.setSpacing(10)
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)

        self.usuario = QtWidgets.QLineEdit(str(cfg.get("usuario", "")))
        self.usuario.setPlaceholderText("(vacío = usuario de Windows)")

        self.empresa_defecto = QtWidgets.QComboBox()
        _fill_empresas_combo(self.empresa_defecto, db)
        actual = str(cfg.get("empresa_defecto", ""))
        idx = self.empresa_defecto.findData(actual)
        if idx >= 0:
            self.empresa_defecto.setCurrentIndex(idx)
        elif actual:
            self.empresa_defecto.setCurrentText(actual)

        self.poll = QtWidgets.QDoubleSpinBox()
        self.poll.setRange(0.2, 10.0)
        self.poll.setSingleStep(0.5)
        self.poll.setValue(float(cfg.get("poll_foreground", 1.0)))

        self.interval = QtWidgets.QSpinBox()
        self.interval.setRange(5, 600)
        self.interval.setValue(int(cfg.get("capture_interval", 30)))

        self.merge_gap = QtWidgets.QSpinBox()
        self.merge_gap.setRange(0, 3600)
        self.merge_gap.setValue(int(cfg.get("merge_gap", 300)))
        self.merge_gap.setToolTip(
            "Hueco máximo para fusionar segmentos consecutivos de la misma "
            "empresa en un único registro."
        )

        self.afk_timeout = QtWidgets.QSpinBox()
        self.afk_timeout.setRange(30, 3600)
        self.afk_timeout.setValue(int(cfg.get("afk_timeout", 120)))
        self.afk_timeout.setToolTip(
            "Inactividad (sin teclado/ratón) tras la cual el tiempo deja de "
            "contar como trabajo."
        )

        self.min_segment = QtWidgets.QSpinBox()
        self.min_segment.setRange(0, 300)
        self.min_segment.setValue(int(cfg.get("min_segment", 5)))
        self.min_segment.setToolTip(
            "Los segmentos más cortos que este valor se descartan."
        )

        self.calendar_source = QtWidgets.QComboBox()
        for etiqueta, valor in [
            ("Ninguno", "none"), ("Outlook", "outlook"), ("Google", "google"),
        ]:
            self.calendar_source.addItem(etiqueta, valor)
        idx = self.calendar_source.findData(
            str(cfg.get("calendar_source", "outlook"))
        )
        if idx >= 0:
            self.calendar_source.setCurrentIndex(idx)

        self.google_creds = QtWidgets.QLineEdit(
            str(cfg.get("google_credentials", ""))
        )
        self.google_creds.setPlaceholderText(
            "credentials.json de Google (solo si el origen es Google)"
        )
        examinar = QtWidgets.QPushButton("Examinar…")
        examinar.clicked.connect(self._pick_credentials)
        creds_box = QtWidgets.QWidget()
        creds_layout = QtWidgets.QHBoxLayout(creds_box)
        creds_layout.setContentsMargins(0, 0, 0, 0)
        creds_layout.setSpacing(6)
        creds_layout.addWidget(self.google_creds, 1)
        creds_layout.addWidget(examinar)
        self._creds_box = creds_box

        self.miniatura = QtWidgets.QCheckBox("Guardar miniatura de las regiones")
        self.miniatura.setChecked(bool(cfg.get("guardar_miniatura", True)))

        form.addRow("Usuario:", self.usuario)
        form.addRow("Empresa por defecto:", self.empresa_defecto)
        form.addRow("Sondeo de ventana (s):", self.poll)
        form.addRow("Intervalo de captura (s):", self.interval)
        form.addRow("Fusión de segmentos (s):", self.merge_gap)
        form.addRow("Inactividad / AFK (s):", self.afk_timeout)
        form.addRow("Duración mínima (s):", self.min_segment)
        form.addRow("Origen de calendario:", self.calendar_source)
        form.addRow("Credenciales Google:", self._creds_box)
        form.addRow("", self.miniatura)

        outer.addLayout(form)
        outer.addStretch(1)

        # El campo de credenciales solo se muestra si el origen es Google.
        self.calendar_source.currentIndexChanged.connect(
            self._update_creds_visible
        )
        self._update_creds_visible()

    def _update_creds_visible(self) -> None:
        es_google = self.calendar_source.currentData() == "google"
        self._form.setRowVisible(self._creds_box, es_google)

    def _pick_credentials(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Seleccionar credentials.json", "", "JSON (*.json)"
        )
        if path:
            self.google_creds.setText(path)

    def save(self) -> None:
        save_config(
            {
                "usuario": self.usuario.text().strip(),
                "empresa_defecto": _combo_codempresa(self.empresa_defecto),
                "poll_foreground": self.poll.value(),
                "capture_interval": self.interval.value(),
                "merge_gap": self.merge_gap.value(),
                "afk_timeout": self.afk_timeout.value(),
                "min_segment": self.min_segment.value(),
                "apps_reunion": load_config().get("apps_reunion", []),
                "calendar_source": self.calendar_source.currentData(),
                "google_credentials": self.google_creds.text().strip(),
                "guardar_miniatura": self.miniatura.isChecked(),
            }
        )


class EmpresasTab(QtWidgets.QWidget):
    """Catálogo de empresas: alta manual, importación de Excel y Biloop.

    El acceso a Biloop está integrado aquí: se introducen las credenciales,
    se comprueba el acceso y, si el portal responde, las empresas autorizadas
    se vuelcan en el catálogo. Las credenciales pueden recordarse para no
    pedirlas en cada arranque del equipo.
    """

    def __init__(self, db: WorkAuditDB) -> None:
        super().__init__()
        self.db = db
        cfg = load_config()

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        hint = QtWidgets.QLabel(
            "Catálogo de empresas cliente. Puedes crearlas a mano, importarlas "
            "de un Excel (columnas CODEMPRESA, NOMEMPRESA, CIF) o traerlas del "
            "portal Biloop comprobando tu acceso más abajo."
        )
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Código", "Nombre", "CIF", "Programa"]
        )
        _style_table(self.table)
        self.table.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.table, 1)

        botones = QtWidgets.QHBoxLayout()
        botones.setSpacing(8)
        add_btn = QtWidgets.QPushButton("Añadir")
        add_btn.clicked.connect(self._add)
        del_btn = QtWidgets.QPushButton("Eliminar")
        del_btn.clicked.connect(self._delete)
        excel_btn = QtWidgets.QPushButton("Importar de Excel…")
        excel_btn.clicked.connect(self._import_excel)
        botones.addWidget(add_btn)
        botones.addWidget(del_btn)
        botones.addStretch(1)
        botones.addWidget(excel_btn)
        layout.addLayout(botones)

        layout.addWidget(self._build_biloop_box(cfg))

        self.refresh()

    # -- sección Biloop -----------------------------------------------------

    def _build_biloop_box(self, cfg: dict) -> QtWidgets.QGroupBox:
        """Construye el panel «Acceso a Biloop» integrado en la pestaña."""
        box = QtWidgets.QGroupBox("Acceso a Biloop")
        box.setStyleSheet(
            "QGroupBox { border: 1px solid #EDEBE9; border-radius: 6px; "
            "margin-top: 8px; padding: 12px; } "
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; }"
        )
        outer = QtWidgets.QVBoxLayout(box)
        outer.setSpacing(8)

        form = QtWidgets.QFormLayout()
        form.setSpacing(8)
        self.url = QtWidgets.QLineEdit(str(cfg.get("biloop_url", "")))
        self.url.setPlaceholderText("https://auren.biloop.es")
        self.key = QtWidgets.QLineEdit(
            str(cfg.get("biloop_subscription_key", ""))
        )
        self.key.setPlaceholderText("Subscription Key (UUID)")
        self.usuario = QtWidgets.QLineEdit(str(cfg.get("biloop_usuario", "")))
        self.password = QtWidgets.QLineEdit()
        self.password.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        form.addRow("URL del portal:", self.url)
        form.addRow("Subscription Key:", self.key)
        form.addRow("Usuario:", self.usuario)
        form.addRow("Contraseña:", self.password)
        outer.addLayout(form)

        self.key_tipo_usuario = QtWidgets.QCheckBox(
            "Mi API Key es de tipo USUARIO (no enviar credenciales al portal)"
        )
        self.key_tipo_usuario.setChecked(
            bool(cfg.get("biloop_key_tipo_usuario"))
        )
        self.key_tipo_usuario.toggled.connect(self._on_tipo_changed)
        self.recordar = QtWidgets.QCheckBox(
            "Recordar mis credenciales en este equipo"
        )
        self.recordar.setChecked(bool(cfg.get("biloop_recordar")))
        self.autoupdate = QtWidgets.QCheckBox(
            "Comprobar el acceso y actualizar la lista al iniciar la aplicación"
        )
        self.autoupdate.setChecked(bool(cfg.get("empresas_autoupdate", False)))
        outer.addWidget(self.key_tipo_usuario)
        outer.addWidget(self.recordar)
        outer.addWidget(self.autoupdate)

        self.biloop_status = QtWidgets.QLabel("")
        self.biloop_status.setWordWrap(True)
        outer.addWidget(self.biloop_status)

        fila = QtWidgets.QHBoxLayout()
        fila.setSpacing(8)
        olvidar_btn = QtWidgets.QPushButton("Olvidar credenciales")
        olvidar_btn.clicked.connect(self._olvidar_biloop)
        conectar_btn = QtWidgets.QPushButton("Comprobar acceso y ver empresas")
        conectar_btn.setObjectName("primary")
        conectar_btn.clicked.connect(self._conectar_biloop)
        fila.addWidget(olvidar_btn)
        fila.addStretch(1)
        fila.addWidget(conectar_btn)
        outer.addLayout(fila)

        # Precargar la contraseña guardada si procede.
        self._on_tipo_changed(self.key_tipo_usuario.isChecked())
        if cfg.get("biloop_recordar"):
            usuario = str(cfg.get("biloop_usuario", ""))
            if usuario:
                pwd = leer_password(usuario)
                if pwd:
                    self.password.setText(pwd)
        return box

    def _on_tipo_changed(self, checked: bool) -> None:
        """Con key tipo USUARIO no se envían credenciales: campos desactivados."""
        self.usuario.setEnabled(not checked)
        self.password.setEnabled(not checked)

    def _set_status(self, texto: str, color: str = "#605E5C") -> None:
        self.biloop_status.setText(texto)
        self.biloop_status.setStyleSheet(f"color: {color};")

    def _persistir_biloop(self) -> None:
        """Guarda la configuración de Biloop y la contraseña según «recordar»."""
        recordar = self.recordar.isChecked()
        tipo_usuario = self.key_tipo_usuario.isChecked()
        usuario_txt = self.usuario.text().strip()
        save_config(
            {
                "biloop_url": self.url.text().strip(),
                "biloop_subscription_key": self.key.text().strip(),
                "biloop_key_tipo_usuario": tipo_usuario,
                "biloop_recordar": recordar,
                "biloop_usuario": usuario_txt if recordar else "",
                "empresas_autoupdate": self.autoupdate.isChecked(),
            }
        )
        if recordar and not tipo_usuario and usuario_txt:
            guardar_password(usuario_txt, self.password.text())
        else:
            olvidar_password(usuario_txt)

    def _conectar_biloop(self) -> None:
        """Comprueba el acceso a Biloop y vuelca las empresas autorizadas.

        No entra en ninguna empresa: solo valida que el login es correcto y
        muestra el catálogo que el portal autoriza para esas credenciales.
        """
        url = self.url.text().strip()
        key = self.key.text().strip()
        if not url or not key:
            QtWidgets.QMessageBox.warning(
                self,
                "work-audit",
                "Indica la URL del portal y la Subscription Key.",
            )
            return

        tipo_usuario = self.key_tipo_usuario.isChecked()
        user = None if tipo_usuario else (self.usuario.text().strip() or None)
        password = None if tipo_usuario else (self.password.text() or None)

        self._set_status("Conectando con Biloop…")
        QtWidgets.QApplication.setOverrideCursor(
            QtCore.Qt.CursorShape.WaitCursor
        )
        QtWidgets.QApplication.processEvents()
        try:
            from .. import biloop
            cli = biloop.BiloopClient(url, key)
            token = cli.obtener_token(user, password)
            empresas = cli.listar_empresas(token)
        except Exception as e:  # noqa: BLE001
            QtWidgets.QApplication.restoreOverrideCursor()
            self._set_status("No se pudo conectar con Biloop.", "#A4262C")
            box = QtWidgets.QMessageBox(self)
            box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
            box.setWindowTitle("Acceso a Biloop")
            box.setText(str(e))
            box.setInformativeText(biloop.diag_config(url, key))
            box.exec()
            return
        QtWidgets.QApplication.restoreOverrideCursor()

        self._persistir_biloop()
        from ..sync import importar_empresas_biloop
        res = importar_empresas_biloop(self.db, empresas)
        self.refresh()
        baja = (
            f", {res['deleted']} dada(s) de baja" if res["deleted"] else ""
        )
        self._set_status(
            f"✓ Conectado al portal · {len(empresas)} empresa(s) autorizada(s) · "
            f"{res['upserted']} en el catálogo{baja}.",
            "#107C10",
        )

    def _olvidar_biloop(self) -> None:
        usuario = self.usuario.text().strip()
        olvidar_password(usuario)
        save_config({"biloop_recordar": False, "biloop_usuario": ""})
        self.password.clear()
        self.recordar.setChecked(False)
        self._set_status("Credenciales olvidadas en este equipo.")

    def refresh(self) -> None:
        empresas = self.db.all_empresas()
        self.table.setRowCount(len(empresas))
        for row, emp in enumerate(empresas):
            self.table.setItem(
                row, 0, QtWidgets.QTableWidgetItem(emp["CODEMPRESA"])
            )
            self.table.setItem(
                row, 1, QtWidgets.QTableWidgetItem(emp.get("NOMEMPRESA") or "")
            )
            self.table.setItem(
                row, 2, QtWidgets.QTableWidgetItem(emp.get("CIF") or "")
            )
            self.table.setItem(
                row, 3, QtWidgets.QTableWidgetItem(emp.get("PROGRAMA") or "")
            )

    def _add(self) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        for col in range(4):
            self.table.setItem(row, col, QtWidgets.QTableWidgetItem(""))
        self.table.setCurrentCell(row, 0)
        self.table.editItem(self.table.item(row, 0))

    def _delete(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 0)
        cod = item.text().strip() if item else ""
        if cod and self.db.get_empresa(cod):
            confirm = QtWidgets.QMessageBox.question(
                self, "work-audit", f"¿Eliminar la empresa «{cod}»?"
            )
            if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
                return
            self.db.delete_empresa(cod)
        self.table.removeRow(row)

    def _import_excel(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Seleccionar Excel de empresas", "", "Excel (*.xlsx *.xlsm)"
        )
        if not path:
            return
        try:
            from ..empresas_import import import_excel
            empresas = import_excel(path)
        except Exception as e:  # noqa: BLE001
            QtWidgets.QMessageBox.warning(
                self, "work-audit", f"No se pudo leer el Excel:\n{e}"
            )
            return
        if not empresas:
            QtWidgets.QMessageBox.warning(
                self, "work-audit", "El Excel no contenía empresas."
            )
            return
        self.db.upsert_empresas(empresas, origen="excel")
        self.refresh()
        QtWidgets.QMessageBox.information(
            self, "work-audit", f"Importadas {len(empresas)} empresas del Excel."
        )

    def save(self) -> None:
        empresas = []
        for row in range(self.table.rowCount()):
            cod_item = self.table.item(row, 0)
            cod = cod_item.text().strip() if cod_item else ""
            if not cod:
                continue
            nom_item = self.table.item(row, 1)
            cif_item = self.table.item(row, 2)
            prog_item = self.table.item(row, 3)
            empresas.append(
                {
                    "CODEMPRESA": cod,
                    "NOMEMPRESA": nom_item.text().strip() if nom_item else "",
                    "CIF": cif_item.text().strip() if cif_item else "",
                    "PROGRAMA": prog_item.text().strip() if prog_item else "",
                }
            )
        if empresas:
            self.db.upsert_empresas(empresas)
        self._persistir_biloop()


class ConfigWindow(QtWidgets.QWidget):
    """Ventana de configuración con cabecera y pestañas."""

    def __init__(self, db: Optional[WorkAuditDB] = None) -> None:
        super().__init__()
        self.db = db or WorkAuditDB()
        self.setWindowTitle("work-audit · Configuración")
        self.resize(780, 680)
        self.setStyleSheet(STYLESHEET)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(HeaderBand("Configuración", "Auditoría de trabajos"))

        content = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content)
        content_layout.setContentsMargins(18, 16, 18, 16)
        content_layout.setSpacing(12)

        self.tabs = QtWidgets.QTabWidget()
        self.aplicaciones_tab = AplicacionesTab(self.db)
        self.empresas_tab = EmpresasTab(self.db)
        self.ajustes_tab = AjustesTab(self.db)
        self.tabs.addTab(self.aplicaciones_tab, "Aplicaciones a auditar")
        self.tabs.addTab(self.empresas_tab, "Empresas")
        self.tabs.addTab(self.ajustes_tab, "Ajustes")
        content_layout.addWidget(self.tabs, 1)

        botones = QtWidgets.QHBoxLayout()
        botones.addStretch(1)
        close_btn = QtWidgets.QPushButton("Cerrar")
        close_btn.clicked.connect(self.close)
        save_btn = QtWidgets.QPushButton("Guardar cambios")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self._save)
        botones.addWidget(close_btn)
        botones.addWidget(save_btn)
        content_layout.addLayout(botones)

        root.addWidget(content, 1)

    def _save(self) -> None:
        self.aplicaciones_tab.save()
        self.empresas_tab.save()
        self.ajustes_tab.save()
        self.aplicaciones_tab.refresh()
        self.empresas_tab.refresh()
        QtWidgets.QMessageBox.information(
            self, "work-audit", "Configuración guardada."
        )


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    window = ConfigWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
