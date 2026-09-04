#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI wrapper around services.export_tiles()/merge_tiles() - export a clip
of an AgEA ImageServer at a chosen pixel size, tiling as needed and
mosaicking the tiles back into a single GeoTIFF.

The same tiling logic backs the plugin's own Processing algorithm ("AgEA
Ortofoto > Esporta ritaglio ad alta risoluzione"); this script is a
convenience for running it outside QGIS Desktop, e.g. via the qgis-headless
skill on WSL2/Linux. See services.py's "High-resolution tiled export"
section for why tiling is needed at all, and why pixel sizes finer than
~0.4 m/pixel are refused outright (a resolution floor of the service
itself - confirmed down to 40x40 m requests - not something tiling helps
with).

Usage::

    QT_QPA_PLATFORM=offscreen micromamba run -n qgis python export_tiled.py \\
        --year 2022 \\
        --extent 1576657.7808,4520622.8778,1578803.7272,4521686.3135 \\
        --extent-crs EPSG:3857 \\
        --pixel-size 0.5 \\
        --output /path/to/clip.tif

Or from the QGIS Desktop Python console (paste the whole file, or
``exec(open('export_tiled.py').read())``, then call ``main([...])``) - a
running QGIS already provides ``QgsApplication``, no extra init needed.
"""
import argparse
import glob
import os
import shutil
import sys
import time

from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsRectangle,
)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services import (  # noqa: E402
    BASE_URL,
    DEFAULT_MAX_EMPTY_SPLITS,
    DEFAULT_MAX_TILE_PIXELS,
    DEFAULT_MIN_TILE_PX,
    EMPIRICAL_MIN_PIXEL_SIZE,
    build_export_layer,
    export_tiles,
    merge_tiles,
    transform_extent,
)


def _init_qgis_if_needed():
    """Start a headless QgsApplication unless one is already running (e.g.
    when this script is executed from inside QGIS Desktop's console)."""
    if QgsApplication.instance() is not None:
        return None
    QgsApplication.setPrefixPath(os.environ.get("CONDA_PREFIX", ""), True)
    qgs = QgsApplication([], False)
    qgs.initQgis()
    return qgs


def _parse_extent(text):
    parts = [float(p) for p in text.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("extent must be 'xmin,ymin,xmax,ymax'")
    return QgsRectangle(*parts)


def _on_tile(event, **info):
    if event == "exported":
        print("  tile: {}x{} px OK".format(info["width"], info["height"]), flush=True)
    elif event == "empty":
        print(
            "  tile at {} came back empty at {}x{} px - splitting into 4 and retrying "
            "({} empty-retry level(s) left)...".format(
                info["extent"].toString(2), info["width"], info["height"], info["retries_left"]
            ),
            flush=True,
        )
    elif event == "skipped":
        print(
            "  tile at {} came back empty at {}x{} px; treating as no coverage and skipping.".format(
                info["extent"].toString(2), info["width"], info["height"]
            ),
            flush=True,
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--year", type=int, choices=(2022, 2023, 2024), help="AgEA year (uses the plugin's own ImageServer URL)")
    source.add_argument("--url", help="Custom ImageServer URL, if not one of the AgEA yearly services")
    parser.add_argument("--extent", required=True, type=_parse_extent, help="xmin,ymin,xmax,ymax")
    parser.add_argument("--extent-crs", default="EPSG:3857", help="CRS of --extent (default: EPSG:3857, matching QGIS's 'Save as' dialog default)")
    parser.add_argument("--pixel-size", required=True, type=float, help="Output pixel size in the layer's CRS units (metres for EPSG:3857)")
    parser.add_argument("--output", required=True, help="Final merged GeoTIFF path")
    parser.add_argument("--keep-tiles", action="store_true", help="Do not delete intermediate tiles after merging")
    parser.add_argument("--work-dir", default=None, help="Where to write intermediate tiles (default: a temp dir alongside --output, removed unless --keep-tiles)")
    parser.add_argument("--max-tile-pixels", type=int, default=DEFAULT_MAX_TILE_PIXELS, help="Pre-emptively split any request larger than this many pixels (default: {:,}; a memory/runtime cap, not a server limit)".format(DEFAULT_MAX_TILE_PIXELS))
    parser.add_argument("--min-tile-px", type=int, default=DEFAULT_MIN_TILE_PX, help="Stop retrying an empty tile once both sides are at or below this many pixels (default: {})".format(DEFAULT_MIN_TILE_PX))
    parser.add_argument("--max-empty-splits", type=int, default=DEFAULT_MAX_EMPTY_SPLITS, help="How many times an empty tile may be re-split before it is accepted as real nodata (default: {})".format(DEFAULT_MAX_EMPTY_SPLITS))
    parser.add_argument("--dry-run", action="store_true", help="Only print the extent/resolution that would be requested, do not contact the server")
    parser.add_argument("--force", action="store_true", help="Proceed even if --pixel-size is finer than the empirically-confirmed floor ({} m) - see services.py".format(EMPIRICAL_MIN_PIXEL_SIZE))
    args = parser.parse_args(argv)

    if args.pixel_size < EMPIRICAL_MIN_PIXEL_SIZE and not args.force:
        parser.error(
            "--pixel-size {} is finer than {} m/pixel, which testing found this service "
            "never actually returns data for - regardless of extent or tiling (see "
            "services.py). Use --pixel-size {} or coarser, or pass --force to try anyway.".format(
                args.pixel_size, EMPIRICAL_MIN_PIXEL_SIZE, EMPIRICAL_MIN_PIXEL_SIZE
            )
        )

    qgs = _init_qgis_if_needed()
    try:
        url = args.url or BASE_URL.format(year=args.year)
        layer = build_export_layer(url)

        extent_crs = QgsCoordinateReferenceSystem(args.extent_crs)
        extent = transform_extent(args.extent, extent_crs, layer.crs())

        est_w = round(extent.width() / args.pixel_size)
        est_h = round(extent.height() / args.pixel_size)
        print(
            "Extent: {} ({})  ->  {}x{} px total at {} m/px".format(
                extent.toString(2), layer.crs().authid(), est_w, est_h, args.pixel_size
            )
        )
        if args.dry_run:
            print("(--dry-run: no data downloaded)")
            return

        work_dir = args.work_dir or (os.path.splitext(args.output)[0] + "_tiles")
        t0 = time.time()
        tiles = export_tiles(
            layer, layer.crs(), extent, args.pixel_size, work_dir,
            max_tile_pixels=args.max_tile_pixels,
            min_tile_px=args.min_tile_px,
            max_empty_splits=args.max_empty_splits,
            on_tile=_on_tile,
        )
        print("{} valid tile(s) in {:.1f}s".format(len(tiles), time.time() - t0))

        print("Merging into {}...".format(args.output))
        merge_tiles(tiles, args.output)
        print("Done: {}".format(args.output))

        if not args.keep_tiles:
            shutil.rmtree(work_dir, ignore_errors=True)
    finally:
        if qgs is not None:
            qgs.exitQgis()


if __name__ == "__main__":
    main()
