# -*- coding: utf-8 -*-
"""AgEA ImageServer definitions and loading logic."""

import os
from datetime import datetime

from qgis.core import (
    QgsCoordinateTransform,
    QgsProject,
    QgsRasterFileWriter,
    QgsRasterLayer,
    QgsRasterPipe,
    QgsRectangle,
)

GROUP_NAME = 'AGEA 2022-23-24'

BASE_URL = (
    'https://geoportale.agea.gov.it/image/rest/services/AgEA/'
    'Ortofoto_AgEA_{year}/ImageServer'
)

YEARS = (2022, 2023, 2024)

# AgEA publishes these orthophoto services under CC BY 4.0. That license
# permits resampling to a different pixel size (it's an "Adapt" under the
# license, no NoDerivs/ShareAlike clause involved) but requires attribution,
# including - per its 3(a)(1)(C) - noting that the material was changed from
# the original. attribution_metadata()/write_attribution_sidecar() below (see
# the "High-resolution tiled export" section) exist to make that obligation
# hard to miss when exporting a clip at a custom resolution.
LICENSE_URL = 'https://creativecommons.org/licenses/by/4.0/'

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


# --- High-resolution tiled export ---------------------------------------
#
# A single `exportImage` request against an AgEA ImageServer silently comes
# back fully transparent/nodata once the requested pixel size is finer than
# roughly 0.4 m/pixel - confirmed by bisecting requests as small as 40x40 m,
# so it is a resolution floor of the service itself, not a request-size
# limit (the documented maxImageWidth/maxImageHeight capabilities and a
# single request's total pixel count both turned out not to be the
# operative constraint: a single 1-billion-pixel request at 0.5 m/pixel
# came back valid). All three yearly services report the same native
# pixelSizeX/Y of 0.2 m in their REST capabilities, but that resolution is
# not actually deliverable through this API.
#
# What *does* still need tiling is real nodata: a requested extent can
# genuinely spill past the flown coverage (a region border, open sea, ...),
# which comes back blank no matter how small the tile or how coarse the
# pixel size. export_tiles() below splits into quadrants to isolate and
# skip only the genuinely-uncovered parts, and also splits proactively on
# very large requests to keep memory/runtime bounded - not because size
# itself causes blank output.

EMPIRICAL_MIN_PIXEL_SIZE = 0.4
DEFAULT_MAX_TILE_PIXELS = 50_000_000
DEFAULT_MIN_TILE_PX = 500
DEFAULT_MAX_EMPTY_SPLITS = 2
TILE_CREATION_OPTIONS = ['COMPRESS=DEFLATE', 'PREDICTOR=2', 'ZLEVEL=9']


def build_export_layer(url):
    """Open an ImageServer as a standalone raster layer for clip export.

    Not added to any project/group - used by the tiled-export tooling.
    """
    layer = QgsRasterLayer(build_uri(url), 'agea_export_source', 'arcgismapserver')
    if not layer.isValid():
        raise RuntimeError(layer.error().message())
    return layer


def transform_extent(extent, src_crs, dst_crs, project=None):
    """Reproject `extent` from src_crs to dst_crs (a no-op if they match)."""
    if src_crs.authid() == dst_crs.authid():
        return QgsRectangle(extent)
    transform = QgsCoordinateTransform(src_crs, dst_crs, project or QgsProject.instance())
    return transform.transformBoundingBox(extent)


def tile_is_valid(path):
    """Heuristic matching every empty response observed: a genuinely blank
    tile has band 1 (and every other band) pegged at 0."""
    layer = QgsRasterLayer(path, 'agea_export_check')
    if not layer.isValid():
        return False
    return layer.dataProvider().bandStatistics(1).maximumValue > 0


def export_tile(layer, crs, extent, pixel_size, out_path):
    """Write a single GeoTIFF tile covering `extent` at `pixel_size`."""
    width = max(1, round(extent.width() / pixel_size))
    height = max(1, round(extent.height() / pixel_size))

    pipe = QgsRasterPipe()
    pipe.set(layer.dataProvider().clone())
    writer = QgsRasterFileWriter(out_path)
    writer.setCreateOptions(TILE_CREATION_OPTIONS)
    writer.writeRaster(pipe, width, height, extent, crs)
    return width, height


def split_in_quadrants(extent):
    xmin, ymin, xmax, ymax = (
        extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum(),
    )
    xmid, ymid = (xmin + xmax) / 2.0, (ymin + ymax) / 2.0
    return [
        QgsRectangle(xmin, ymid, xmid, ymax),  # top-left
        QgsRectangle(xmid, ymid, xmax, ymax),  # top-right
        QgsRectangle(xmin, ymin, xmid, ymid),  # bottom-left
        QgsRectangle(xmid, ymin, xmax, ymid),  # bottom-right
    ]


def export_tiles(layer, crs, extent, pixel_size, work_dir,
                  max_tile_pixels=DEFAULT_MAX_TILE_PIXELS,
                  min_tile_px=DEFAULT_MIN_TILE_PX,
                  max_empty_splits=DEFAULT_MAX_EMPTY_SPLITS,
                  on_tile=None, should_cancel=None):
    """Recursively export `extent` into one or more GeoTIFF tiles.

    Splits into quadrants whenever a request would exceed `max_tile_pixels`
    (unconditional - just to bound memory/runtime), or whenever a tile comes
    back empty (bounded by `max_empty_splits` and `min_tile_px`, so a large
    genuinely-uncovered area is not probed exhaustively down to the pixel).

    `on_tile(event, **info)` if given is called for progress reporting -
    events are 'exported', 'empty' (about to retry smaller) and 'skipped'
    (given up, treated as real nodata). `should_cancel()` if given is polled
    between tiles to support early abort.

    Returns the list of valid tile paths (possibly empty).
    """
    os.makedirs(work_dir, exist_ok=True)
    counter = [0]

    def cancelled():
        return should_cancel() if should_cancel is not None else False

    def emit(event, **info):
        if on_tile is not None:
            on_tile(event, **info)

    def recurse(sub_extent, empty_splits_left):
        if cancelled():
            return []

        width = max(1, round(sub_extent.width() / pixel_size))
        height = max(1, round(sub_extent.height() / pixel_size))
        too_small_to_split = width <= min_tile_px and height <= min_tile_px

        if width * height > max_tile_pixels and not too_small_to_split:
            tiles = []
            for quadrant in split_in_quadrants(sub_extent):
                if cancelled():
                    break
                tiles.extend(recurse(quadrant, empty_splits_left))
            return tiles

        counter[0] += 1
        out_path = os.path.join(work_dir, 'tile_{:04d}.tif'.format(counter[0]))
        export_tile(layer, crs, sub_extent, pixel_size, out_path)

        if tile_is_valid(out_path):
            emit('exported', path=out_path, width=width, height=height, extent=sub_extent)
            return [out_path]

        os.remove(out_path)
        counter[0] -= 1  # reuse the number for whatever retry tile comes next

        if too_small_to_split or empty_splits_left <= 0:
            emit('skipped', width=width, height=height, extent=sub_extent)
            return []

        emit('empty', width=width, height=height, extent=sub_extent, retries_left=empty_splits_left)
        tiles = []
        for quadrant in split_in_quadrants(sub_extent):
            if cancelled():
                break
            tiles.extend(recurse(quadrant, empty_splits_left - 1))
        return tiles

    return recurse(extent, max_empty_splits)


def merge_tiles(tile_paths, output_path, creation_options=TILE_CREATION_OPTIONS, metadata=None):
    """Mosaic `tile_paths` into a single compressed GeoTIFF at output_path.

    `metadata`, if given, is a dict of GDAL metadata items to stamp onto the
    output - see attribution_metadata(). Standard TIFFTAG_* keys (COPYRIGHT,
    IMAGEDESCRIPTION, SOFTWARE, ...) are written by the GTiff driver as real
    TIFF tags, not just GDAL sidecar metadata, so they survive round-trips
    through other tools and stay attached even if the file is copied or
    renamed on its own.
    """
    from osgeo import gdal

    if not tile_paths:
        raise RuntimeError('No valid tiles were produced - nothing to merge.')

    vrt_path = output_path + '.vrt'
    gdal.BuildVRT(vrt_path, tile_paths)
    translate_kwargs = {'creationOptions': creation_options}
    if metadata:
        translate_kwargs['metadataOptions'] = [
            '{}={}'.format(key, value) for key, value in metadata.items()
        ]
    gdal.Translate(output_path, vrt_path, **translate_kwargs)
    os.remove(vrt_path)


# --- CC BY 4.0 attribution -----------------------------------------------

ATTRIBUTION_NOTE = (
    "Fonte: AgEA (Agenzia per le Erogazioni in Agricoltura), servizio {source_url}. "
    "Licenza: CC BY 4.0 ({license_url}). "
    "Dato modificato rispetto all'originale: ricampionato a {pixel_size} m/pixel "
    '(risoluzione nativa dichiarata dal servizio: 0.2 m/pixel).'
)


def attribution_metadata(source_url, pixel_size):
    """GDAL metadata items to stamp onto an exported GeoTIFF via merge_tiles().

    Keyed on the standard TIFFTAG_* names the GTiff driver recognises, so
    they land as real TIFF tags (visible e.g. via `gdalinfo` or a layer's
    Properties > Metadata in QGIS), not just GDAL-specific sidecar metadata.
    """
    note = ATTRIBUTION_NOTE.format(
        source_url=source_url, license_url=LICENSE_URL, pixel_size=pixel_size)
    return {
        'TIFFTAG_COPYRIGHT': 'AgEA - CC BY 4.0 ({})'.format(LICENSE_URL),
        'TIFFTAG_IMAGEDESCRIPTION': note,
        'TIFFTAG_SOFTWARE': 'AgEA Ortofoto QGIS plugin',
    }


ATTRIBUTION_SIDECAR_TEMPLATE = """\
Ritaglio ortofoto AgEA
=======================

Fonte:                 {source_url}
Estensione esportata:   {extent} ({crs})
Dimensione pixel:       {pixel_size} m/pixel
                        (risoluzione nativa dichiarata dal servizio: 0.2 m/pixel;
                        sotto ~0.4 m/pixel il servizio non eroga dati, quindi
                        questo file e' comunque un ricampionamento rispetto
                        all'originale)
Data export:            {timestamp}

Licenza: Creative Commons Attribution 4.0 International (CC BY 4.0)
         {license_url}

La licenza CC BY 4.0 consente la condivisione e l'adattamento di questo
materiale (incluso il ricampionamento a una dimensione di pixel diversa da
quella originale), anche per uso commerciale, alla sola condizione di darne
attribuzione. In caso di ridistribuzione di questo file o di un suo derivato,
includere:
  - la fonte: AgEA, servizio {source_url}
  - il link alla licenza: {license_url}
  - l'indicazione che il dato e' stato modificato rispetto all'originale
    (ricampionato a {pixel_size} m/pixel)

Questo file e' stato generato automaticamente dal plugin QGIS "AgEA Ortofoto"
insieme al GeoTIFF corrispondente (che porta la stessa nota nei tag TIFF
Copyright/ImageDescription).
"""


def write_attribution_sidecar(output_path, source_url, pixel_size, extent, crs):
    """Write a '<output>_licenza.txt' sidecar with the CC BY 4.0 attribution.

    Complements the TIFFTAG_* metadata attribution_metadata() stamps into the
    GeoTIFF itself: the sidecar is the more human-readable copy (visible in a
    plain file browser, no GIS needed), while the embedded tags are the one
    that survives the file being copied or renamed on its own.

    Returns the sidecar's path.
    """
    sidecar_path = os.path.splitext(output_path)[0] + '_licenza.txt'
    text = ATTRIBUTION_SIDECAR_TEMPLATE.format(
        source_url=source_url,
        pixel_size=pixel_size,
        extent=extent.toString(2),
        crs=crs.authid(),
        timestamp=datetime.now().strftime('%Y-%m-%d %H:%M'),
        license_url=LICENSE_URL,
    )
    with open(sidecar_path, 'w', encoding='utf-8') as f:
        f.write(text)
    return sidecar_path
