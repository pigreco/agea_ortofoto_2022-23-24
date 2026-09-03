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

# Approximate region extents in EPSG:4326 (xmin, ymin, xmax, ymax), used only
# to zoom the map canvas to a selected region - not meant for precise spatial
# analysis. Derived from Eurostat GISCO NUTS2 boundaries (NUTS_RG_60M_2021),
# with the Bolzano/Trento NUTS2 split merged back into Trentino-Alto Adige to
# match REGIONS_BY_YEAR.
REGION_EXTENT_4326 = {
    'Abruzzo': (13.0306, 41.6879, 14.7796, 42.8946),
    'Basilicata': (15.3350, 39.9235, 16.8673, 41.1399),
    'Calabria': (15.6528, 37.9310, 17.1100, 40.1191),
    'Campania': (13.7608, 40.0428, 15.7139, 41.4864),
    'Emilia-Romagna': (9.2001, 43.7538, 12.7507, 45.1326),
    'Friuli-Venezia Giulia': (12.4005, 45.5875, 13.9032, 46.6343),
    'Lazio': (11.4499, 41.2232, 13.9779, 42.8347),
    'Liguria': (7.5298, 43.7840, 10.0188, 44.6135),
    'Lombardia': (8.5136, 44.6861, 11.4268, 46.5798),
    'Marche': (12.2139, 42.6893, 13.9157, 43.9697),
    'Molise': (13.9410, 41.3825, 15.1382, 42.0700),
    'Piemonte': (6.6301, 44.0615, 9.2030, 46.4522),
    'Puglia': (15.0077, 39.8804, 18.4343, 41.9270),
    'Sardegna': (8.2316, 38.9578, 9.7494, 41.1960),
    'Sicilia': (11.7600, 36.6104, 15.3432, 38.1933),
    'Toscana': (9.6867, 42.3777, 12.2838, 44.4537),
    'Trentino-Alto Adige': (10.4528, 45.6971, 12.4779, 47.0807),
    'Umbria': (11.8950, 42.3988, 13.2353, 43.6108),
    "Valle d'Aosta": (6.8024, 45.4685, 7.9366, 45.9224),
    'Veneto': (10.6547, 44.7926, 13.0988, 46.6798),
}


def region_extent(region):
    """Return the region's approximate (xmin, ymin, xmax, ymax) in EPSG:4326."""
    return REGION_EXTENT_4326[region]


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
