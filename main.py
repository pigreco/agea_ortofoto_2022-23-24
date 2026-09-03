# -*- coding: utf-8 -*-
"""Main plugin module."""

import os

from qgis.core import Qgis
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .region_dialog import RegionDialog
from .services import GROUP_NAME, YEARS, YEAR_BY_REGION, load_all, load_year


class AgeaOrtofoto:
    """Load AgEA orthophoto image services with a single click."""

    def __init__(self, iface):
        """Initialize plugin.

        Args:
            iface: QGIS interface instance.
        """
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = self.tr('&AgEA Ortofoto')
        self.toolbar = self.iface.addToolBar('AgeaOrtofotoToolbar')
        self.toolbar.setObjectName('AgeaOrtofotoToolbar')
        self.region_dialog = None

    def tr(self, message):
        """Translate string."""
        return QCoreApplication.translate('AgeaOrtofoto', message)

    def add_action(self, icon_path, text, callback, tooltip=None,
                   enabled=True, add_to_menu=True, add_to_toolbar=True,
                   parent=None):
        """Add a toolbar icon and a menu entry."""
        action = QAction(QIcon(icon_path), text, parent or self.iface.mainWindow())
        action.triggered.connect(callback)
        action.setEnabled(enabled)
        if tooltip:
            action.setToolTip(tooltip)

        if add_to_toolbar:
            self.toolbar.addAction(action)
        if add_to_menu:
            self.iface.addPluginToWebMenu(self.menu, action)

        self.actions.append(action)
        return action

    def initGui(self):
        """Create menu entries and toolbar icons."""
        self.add_action(
            os.path.join(self.plugin_dir, 'icon.png'),
            text=self.tr('Carica Ortofoto AgEA'),
            tooltip=self.tr('Aggiunge le Ortofoto AgEA {first}-{last} '
                            'in un gruppo dedicato').format(
                                first=min(YEARS), last=max(YEARS)),
            callback=self.run,
            parent=self.iface.mainWindow(),
        )
        self.add_action(
            os.path.join(self.plugin_dir, 'icon.png'),
            text=self.tr('Seleziona regione AgEA...'),
            tooltip=self.tr('Carica solo il servizio AgEA che copre una '
                            'singola regione'),
            callback=self.show_region_dialog,
            parent=self.iface.mainWindow(),
        )

    def unload(self):
        """Remove menu entries and toolbar icons."""
        for action in self.actions:
            self.iface.removePluginWebMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)
        self.actions = []
        del self.toolbar
        if self.region_dialog is not None:
            self.region_dialog.close()
            self.region_dialog = None

    def run(self):
        """Load the services and report the outcome in the message bar."""
        bar = self.iface.messageBar()

        try:
            loaded, failed = load_all()
        except Exception as exc:  # pragma: no cover - defensive
            bar.pushMessage(
                self.tr('AgEA Ortofoto'),
                self.tr('Caricamento fallito: {err}').format(err=exc),
                level=Qgis.MessageLevel.Critical,
                duration=8,
            )
            return

        if not loaded:
            bar.pushMessage(
                self.tr('AgEA Ortofoto'),
                self.tr('Nessun servizio raggiungibile. Verifica la '
                        'connessione o le impostazioni proxy di QGIS.'),
                level=Qgis.MessageLevel.Critical,
                duration=8,
            )
            return

        if failed:
            bar.pushMessage(
                self.tr('AgEA Ortofoto'),
                self.tr('Caricati {n} servizi su {tot}. Non disponibili: '
                        '{ko}').format(n=len(loaded),
                                       tot=len(YEARS),
                                       ko=', '.join(failed)),
                level=Qgis.MessageLevel.Warning,
                duration=8,
            )
            return

        bar.pushMessage(
            self.tr('AgEA Ortofoto'),
            self.tr('Gruppo "{group}" pronto. Zooma sotto 1:50.000 per '
                    'vedere le ortofoto.').format(group=GROUP_NAME),
            level=Qgis.MessageLevel.Success,
            duration=6,
        )

    def show_region_dialog(self):
        """Open the region-picker dialog (created lazily, reused)."""
        if self.region_dialog is None:
            self.region_dialog = RegionDialog(self.iface.mainWindow())
            self.region_dialog.load_requested.connect(
                self._on_region_load_requested)

        self.region_dialog.show()
        self.region_dialog.raise_()
        self.region_dialog.activateWindow()

    def _on_region_load_requested(self, region):
        """Handle a selection from the region dialog.

        `region` is None for the "all regions" entry, which just reuses
        the one-click `run()` path; otherwise only the year covering that
        region is loaded.
        """
        if region is None:
            self.run()
            return

        bar = self.iface.messageBar()
        year = YEAR_BY_REGION[region]

        try:
            layer = load_year(year)
        except Exception as exc:  # pragma: no cover - defensive
            bar.pushMessage(
                self.tr('AgEA Ortofoto'),
                self.tr('Caricamento fallito: {err}').format(err=exc),
                level=Qgis.MessageLevel.Critical,
                duration=8,
            )
            return

        if layer is None:
            bar.pushMessage(
                self.tr('AgEA Ortofoto'),
                self.tr('Servizio {year} (per {region}) non '
                        'raggiungibile.').format(year=year, region=region),
                level=Qgis.MessageLevel.Critical,
                duration=8,
            )
            return

        bar.pushMessage(
            self.tr('AgEA Ortofoto'),
            self.tr('Ortofoto AgEA {year} caricata: copre {region} (e le '
                    'altre regioni riprese nello stesso anno). Zooma sotto '
                    '1:50.000 per vederla.').format(year=year, region=region),
            level=Qgis.MessageLevel.Success,
            duration=6,
        )
