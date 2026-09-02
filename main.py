# -*- coding: utf-8 -*-
"""Main plugin module."""

import os

from qgis.core import Qgis
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .services import GROUP_NAME, YEARS, load_all


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

    def unload(self):
        """Remove menu entries and toolbar icons."""
        for action in self.actions:
            self.iface.removePluginWebMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)
        self.actions = []
        del self.toolbar

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
