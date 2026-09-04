# -*- coding: utf-8 -*-
"""Processing provider registering the AgEA Ortofoto algorithms."""
import os

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

from .tiled_export_algorithm import TiledExportAlgorithm


class AgeaOrtofotoProvider(QgsProcessingProvider):

    def id(self):
        return 'agea_ortofoto'

    def name(self):
        return 'AgEA Ortofoto'

    def icon(self):
        icon_path = os.path.join(os.path.dirname(__file__), 'icon.png')
        return QIcon(icon_path) if os.path.exists(icon_path) else super().icon()

    def loadAlgorithms(self):
        self.addAlgorithm(TiledExportAlgorithm())
