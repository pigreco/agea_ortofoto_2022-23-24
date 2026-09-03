# -*- coding: utf-8 -*-
"""Region-picker dialog: load only the AgEA service covering one region."""

from qgis.PyQt.QtCore import QCoreApplication, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)

from .services import ALL_REGIONS, YEAR_BY_REGION


class RegionDialog(QDialog):
    """Non-modal dialog to pick a region, or "all regions" at once.

    Stays open after a load so the user can pick another region without
    reopening it; `load_requested` carries the region name, or None when
    the "all regions" entry is chosen.
    """

    load_requested = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr('AgEA Ortofoto – Seleziona regione'))

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(self.tr(
            "Seleziona una regione per caricare solo il servizio "
            "dell'anno che la copre, oppure carica tutte e tre le "
            "annualita'.")))

        self.combo = QComboBox(self)
        self.combo.addItem(self.tr('Tutte le regioni (2022-23-24)'), None)
        for region in ALL_REGIONS:
            year = YEAR_BY_REGION[region]
            self.combo.addItem(
                '{region} ({year})'.format(region=region, year=year),
                region)
        layout.addWidget(self.combo)

        buttons = QDialogButtonBox(self)
        self.load_button = buttons.addButton(
            self.tr('Carica'), QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Close)
        self.load_button.clicked.connect(self._emit_load_requested)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)

    def tr(self, message):
        """Translate string."""
        return QCoreApplication.translate('RegionDialog', message)

    def _emit_load_requested(self):
        self.load_requested.emit(self.combo.currentData())
