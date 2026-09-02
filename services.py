# -*- coding: utf-8 -*-
"""AgEA ImageServer definitions and loading logic."""

from qgis.core import QgsProject, QgsRasterLayer

GROUP_NAME = 'AGEA 2022-23-24'

BASE_URL = (
    'https://geoportale.agea.gov.it/image/rest/services/AgEA/'
    'Ortofoto_AgEA_{year}/ImageServer'
)

YEARS = (2022, 2023, 2024)


def build_uri(url):
    """Build the arcgismapserver URI for an ImageServer endpoint.

    Both `layer` and `format` must stay empty: an ImageServer has no numbered
    sub-layers, and an explicit format overrides the server default (jpgpng),
    which is the one handling nodata correctly. Filling either parameter makes
    the service return fully transparent images.
    """
    return "format='' layer='' url='{url}'".format(url=url)


def existing_group(root):
    """Return the plugin group if already present in the layer tree."""
    return root.findGroup(GROUP_NAME)


def load_all(remove_existing=True):
    """Load the three AgEA services into a dedicated group.

    Args:
        remove_existing: drop a previous group with the same name first,
            so repeated runs do not stack duplicates.

    Returns:
        (loaded, failed): lists of layer names.
    """
    project = QgsProject.instance()
    root = project.layerTreeRoot()

    if remove_existing:
        previous = existing_group(root)
        if previous is not None:
            for child in previous.findLayers():
                project.removeMapLayer(child.layerId())
            root.removeChildNode(previous)

    group = root.insertGroup(0, GROUP_NAME)

    loaded, failed = [], []

    # Reversed so the most recent year ends up on top of the group.
    for year in reversed(YEARS):
        name = 'Ortofoto AgEA {year}'.format(year=year)
        url = BASE_URL.format(year=year)

        layer = QgsRasterLayer(build_uri(url), name, 'arcgismapserver')

        if not layer.isValid():
            failed.append(name)
            continue

        project.addMapLayer(layer, False)
        node = group.addLayer(layer)
        # Only the newest year is visible, to avoid opaque stacking.
        node.setItemVisibilityChecked(year == max(YEARS))
        loaded.append(name)

    if not loaded:
        root.removeChildNode(group)

    return loaded, failed
