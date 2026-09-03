# -*- coding: utf-8 -*-
"""Main plugin module."""

import os

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProject,
    QgsRectangle,
)
from qgis.PyQt.QtCore import QCoreApplication, QTimer
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .region_dialog import RegionDialog
from .services import (
    GROUP_NAME,
    YEARS,
    YEAR_BY_REGION,
    load_all,
    load_year,
    region_extent,
)


class AgeaOrtofoto:
    """Load AgEA orthophoto image services: all years, or a single region."""

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
        """Create the single menu entry and toolbar icon."""
        self.add_action(
            os.path.join(self.plugin_dir, 'icon.png'),
            text=self.tr('Carica Ortofoto AgEA'),
            tooltip=self.tr('Carica le Ortofoto AgEA {first}-{last}: tutte '
                            'e tre le annualita, oppure solo quella di una '
                            'regione scelta').format(
                                first=min(YEARS), last=max(YEARS)),
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
        region is loaded. Either way, bring the QGIS main window (canvas
        and message bar) back to the front afterwards, so the result is
        visible without having to move or close the region dialog.
        """
        if region is None:
            self.run()
        else:
            self._load_region(region)

        main_window = self.iface.mainWindow()
        main_window.raise_()
        main_window.activateWindow()

    def _load_region(self, region):
        """Load the single year covering `region` and zoom to its extent."""
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

        # Deferred to the next event-loop tick: when this is the first
        # layer ever added to an empty project, QGIS's own "zoom to the
        # new layer's extent" behaviour runs via a queued call and would
        # otherwise override an immediate setExtent() here.
        QTimer.singleShot(0, lambda: self._zoom_to_region(region))

        bar.pushMessage(
            self.tr('AgEA Ortofoto'),
            self.tr('Ortofoto AgEA {year} caricata: copre {region} (e le '
                    'altre regioni riprese nello stesso anno). Se non vedi '
                    "l'immagine, zooma un po' di piu': sotto 1:50.000 "
                    "l'ImageServer non restituisce contenuto.").format(
                        year=year, region=region),
            level=Qgis.MessageLevel.Success,
            duration=6,
        )

    def _zoom_to_region(self, region):
        """Zoom the map canvas to the region's approximate extent.

        Best-effort: the extents in services.py are approximate (meant for
        framing, not analysis), so a zoom failure here should never stop the
        layer from having been loaded successfully.
        """
        try:
            canvas = self.iface.mapCanvas()
            rect = QgsRectangle(*region_extent(region))
            rect.scale(1.05)  # small padding around the region's edges

            wgs84 = QgsCoordinateReferenceSystem('EPSG:4326')
            canvas_crs = canvas.mapSettings().destinationCrs()
            if canvas_crs != wgs84:
                transform = QgsCoordinateTransform(
                    wgs84, canvas_crs, QgsProject.instance())
                rect = transform.transformBoundingBox(rect)

            canvas.setExtent(rect)
            canvas.refresh()
        except Exception:  # pragma: no cover - defensive, best-effort zoom
            pass
