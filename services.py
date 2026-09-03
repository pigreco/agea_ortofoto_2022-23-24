# -*- coding: utf-8 -*-
"""AgEA ImageServer definitions and loading logic."""

from qgis.core import QgsProject, QgsRasterLayer

GROUP_NAME = 'AGEA 2022-23-24'

BASE_URL = (
    'https://geoportale.agea.gov.it/image/rest/services/AgEA/'
    'Ortofoto_AgEA_{year}/ImageServer'
)

YEARS = (2022, 2023, 2024)

# Which regions each year's ImageServer covers, derived from the distinct
# `regione` values in each service's mosaic dataset footprints (AgEA reshoots
# a different subset of Italy every year, not the whole country at once).
REGIONS_BY_YEAR = {
    2022: ('Abruzzo', 'Liguria', 'Marche', 'Puglia', 'Sardegna', 'Sicilia',
           'Toscana'),
    2023: ('Basilicata', 'Campania', 'Emilia-Romagna',
           'Friuli-Venezia Giulia', 'Lazio', 'Trentino-Alto Adige',
           'Umbria'),
    2024: ('Calabria', 'Lombardia', 'Molise', 'Piemonte', "Valle d'Aosta",
           'Veneto'),
}

# Reverse lookup: region name -> the single year whose service covers it.
YEAR_BY_REGION = {
    region: year
    for year, regions in REGIONS_BY_YEAR.items()
    for region in regions
}

ALL_REGIONS = tuple(sorted(YEAR_BY_REGION))


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


def _layer_name(year):
    return 'Ortofoto AgEA {year}'.format(year=year)


def _build_layer(year):
    """Build the (possibly invalid) raster layer for a given year."""
    name = _layer_name(year)
    url = BASE_URL.format(year=year)
    layer = QgsRasterLayer(build_uri(url), name, 'arcgismapserver')
    return name, layer


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
        name, layer = _build_layer(year)

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


def load_year(year, set_visible=True):
    """Load a single year's service into the group, creating it if needed.

    Used when the user picks a region rather than "load everything": only
    the one ImageServer covering that region's year is added. A layer
    already loaded for the same year is replaced rather than duplicated.

    Returns:
        The QgsRasterLayer, or None if the service could not be reached.
    """
    project = QgsProject.instance()
    root = project.layerTreeRoot()

    group = existing_group(root)
    if group is None:
        group = root.insertGroup(0, GROUP_NAME)

    name, layer = _build_layer(year)
    if not layer.isValid():
        return None

    for child in list(group.findLayers()):
        if child.layer().name() == name:
            # Removing the map layer also removes its layer-tree node, so
            # there is no separate node to remove afterwards.
            project.removeMapLayer(child.layerId())

    project.addMapLayer(layer, False)
    node = group.insertLayer(0, layer)
    node.setItemVisibilityChecked(set_visible)

    return layer
