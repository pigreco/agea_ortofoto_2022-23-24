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
# analysis. Derived from Eurostat GISCO NUTS2 boundaries (NUTS_RG_01M_2021 -
# the 1:1M resolution, needed so minor outlying islands aren't simplified
# away and cut off: Sicilia's Pelagie islands, Puglia's Tremiti, Lazio's
# Ponza/Ventotene). The Bolzano/Trento NUTS2 split is merged back into a
# single Trentino-Alto Adige entry to match REGIONS_BY_YEAR.
REGION_EXTENT_4326 = {
    'Abruzzo': (13.0194, 41.6826, 14.7810, 42.8946),
    'Basilicata': (15.3350, 39.8947, 16.8673, 41.1399),
    'Calabria': (15.6309, 37.9159, 17.2058, 40.1439),
    'Campania': (13.7608, 39.9915, 15.8059, 41.5073),
    'Emilia-Romagna': (9.1981, 43.7319, 12.7550, 45.1385),
    'Friuli-Venezia Giulia': (12.3214, 45.5817, 13.9181, 46.6469),
    'Lazio': (11.4499, 40.7850, 14.0263, 42.8380),
    'Liguria': (7.4953, 43.7766, 10.0704, 44.6762),
    'Lombardia': (8.4984, 44.6801, 11.4268, 46.6347),
    'Marche': (12.1855, 42.6874, 13.9157, 43.9697),
    'Molise': (13.9410, 41.3639, 15.1545, 42.0700),
    'Piemonte': (6.6274, 44.0609, 9.2136, 46.4641),
    'Puglia': (14.9341, 39.7916, 18.5193, 42.1404),
    'Sardegna': (8.1364, 38.8654, 9.8278, 41.3079),
    'Sicilia': (11.9265, 35.4930, 15.6510, 38.8120),
    'Toscana': (9.6867, 42.2382, 12.3710, 44.4727),
    'Trentino-Alto Adige': (10.3826, 45.6734, 12.4779, 47.0917),
    'Umbria': (11.8933, 42.3647, 13.2635, 43.6168),
    "Valle d'Aosta": (6.8024, 45.4685, 7.9394, 45.9876),
    'Veneto': (10.6237, 44.7926, 13.0994, 46.6801),
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
