# -*- coding: utf-8 -*-
"""
AgEA Ortofoto
Carica le Ortofoto AgEA 2022/2023/2024 in un gruppo dedicato.
"""


def classFactory(iface):
    """Load the main plugin class.

    Args:
        iface: QGIS interface instance.
    """
    from .main import AgeaOrtofoto
    return AgeaOrtofoto(iface)
