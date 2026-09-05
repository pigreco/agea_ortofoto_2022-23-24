# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A QGIS plugin (`AgEA Ortofoto`) that loads AGEA's Italian orthophoto ArcGIS ImageServer services
(2022, 2023, 2024) into a dedicated, grouped layer tree entry, using QGIS's native
`arcgismapserver` raster provider (no external dependencies). A single toolbar/menu action opens
a region-picker dialog that either loads all three years at once ("all regions", the default
selection) or just the single year covering a chosen Italian region, zooming the canvas to it.
A Processing algorithm (`AgEA Ortofoto > Esporta ritaglio ad alta risoluzione`) additionally
exports a clip of one of the services to a GeoTIFF at a chosen pixel size, tiling and merging
automatically — see [tiled_export_algorithm.py](tiled_export_algorithm.py) below.

## Architecture

- [__init__.py](__init__.py) — plugin entry point required by QGIS; `classFactory(iface)`
  instantiates `AgeaOrtofoto` from [main.py](main.py).
- [main.py](main.py) — `AgeaOrtofoto` class: QGIS GUI integration (the single toolbar/menu action,
  `initGui`/`unload` lifecycle). `run()` calls `services.load_all()` (the "load everything" path)
  and reports the result via `iface.messageBar()`. `show_region_dialog()` lazily creates and shows
  the [region_dialog.py](region_dialog.py) `RegionDialog`, wiring its `load_requested` signal to
  `_on_region_load_requested()`, which calls `run()` when "all regions" is chosen or
  `_load_region()` otherwise (`services.load_year()` for the region's year, then
  `_zoom_to_region()` — see below); either way it finishes by raising/activating
  `iface.mainWindow()` so the canvas and message bar are visible without having to move or close
  the (still open, reusable) dialog.
  - `_zoom_to_region()` pans/zooms `iface.mapCanvas()` to the region's extent (reprojected from
    EPSG:4326 to the canvas CRS), scheduled via `QTimer.singleShot(0, ...)` rather than called
    immediately. **Why the delay:** when the region's layer is the first ever added to an empty
    project, QGIS's own built-in "zoom to the new layer's extent" behaviour runs via a queued
    call — an immediate `setExtent()` here would get silently overridden by it as soon as control
    returns to the event loop, so the fix is to run *after* that, on the next tick. Best-effort:
    any failure here is swallowed, since the layer is already loaded by that point.
- [region_dialog.py](region_dialog.py) — `RegionDialog`, a small non-modal `QDialog` with a combo
  box listing every region (from `services.ALL_REGIONS`, each annotated with its year) plus an
  "all regions" entry. Emits `load_requested(region_or_None)` on its "Carica" button instead of
  closing, so the user can load several regions/years in a row without reopening it.
- [services.py](services.py) — all the actual logic, independent of GUI wiring:
  - `YEARS` / `BASE_URL` define the three ImageServer endpoints.
  - `REGIONS_BY_YEAR` / `YEAR_BY_REGION` / `ALL_REGIONS` map each of the 20 Italian regions to the
    single year whose ImageServer covers it (AGEA reshoots a different subset of the country each
    year; see the coverage table in [README.md](README.md)).
  - `REGION_EXTENT_4326` / `region_extent()` give each region's approximate EPSG:4326 bounding
    box, used only to zoom the map canvas — not for precise spatial analysis. Sourced from
    Eurostat GISCO NUTS2 boundaries **at 1:1M resolution (`NUTS_RG_01M_2021`)**, with the
    Bolzano/Trento NUTS2 split merged back into a single Trentino-Alto Adige entry to match
    `REGIONS_BY_YEAR`. The 1:1M resolution matters: the coarser 1:60M file initially used here
    simplified away small outlying islands, cutting them out of the bounding box entirely (e.g.
    Sicilia's Pelagie islands/Lampedusa, Puglia's Tremiti, Lazio's Ponza/Ventotene) — if these
    extents are ever regenerated, don't drop back to a coarser resolution.
  - `build_uri()` builds the `arcgismapserver` provider URI. **Both `layer` and `format` must
    stay empty** — an ImageServer has no numbered sub-layers, and setting an explicit format
    overrides the server's default (`jpgpng`), causing the service to return fully transparent
    images. This is the one non-obvious constraint in the codebase.
  - `load_all()` removes any previous `AGEA 2022-23-24` group (so repeated runs don't stack
    duplicates), then adds the three years as raster layers inside a new group, newest year on
    top and the only one visible by default. Returns `(loaded, failed)` name lists so the caller
    can report partial failures (e.g. a service unreachable) without aborting the others.
  - `load_year(year)` adds (or replaces, if already present) a single year's raster layer into the
    existing group, creating the group first if needed. Used by the region picker. **Note:**
    removing a layer via `project.removeMapLayer()` also removes its layer-tree node
    automatically — don't call `group.removeChildNode()` afterwards on the same node, it will
    already be a deleted C++ object.
  - **High-resolution tiled export** (bottom of the file): `export_tiles()` / `merge_tiles()` /
    their helpers back the Processing algorithm below (and the standalone
    [scripts/export_tiled.py](scripts/export_tiled.py) CLI). **The one thing to know:** a single
    `exportImage` request against these services silently comes back fully transparent below
    `EMPIRICAL_MIN_PIXEL_SIZE` (~0.4 m/pixel) — confirmed by bisecting requests as small as 40×40 m,
    so it is a resolution floor of the service itself, not a request-size limit (the documented
    `maxImageWidth`/`maxImageHeight` capabilities, and total pixel count, both turned out not to be
    the operative constraint — a single 1-billion-pixel request at 0.5 m/pixel came back valid). All
    three services report a native `pixelSizeX/Y` of 0.2 m in their REST capabilities, but that
    resolution is not actually deliverable through this API — do not "fix" the floor constant
    without re-verifying against the live service. `export_tiles()` only tiles for a different
    reason: to isolate and skip real nodata (an extent spilling past the flown coverage), bounded by
    `max_empty_splits`/`min_tile_px` so a large genuinely-uncovered area isn't probed exhaustively.
    The same floor is also what caps interactive canvas zoom (not just this export path): the
    `arcgismapserver` provider's own on-screen rendering hits it too, going blank past roughly
    **1:1500** at a standard 96 dpi screen (scale denominator × ~0.0002646 m ≈ requested m/pixel;
    1:1500 ≈ 0.4 m/pixel) — see the README's "Per vedere le immagini" note.
  - **CC BY 4.0 attribution:** AgEA publishes these services under CC BY 4.0, which permits
    resampling to a different pixel size but requires attribution and noting that the material was
    changed from the original. `attribution_metadata()` returns TIFFTAG_* items (COPYRIGHT,
    IMAGEDESCRIPTION, SOFTWARE) that `merge_tiles()`'s optional `metadata` argument stamps into the
    output GeoTIFF as real TIFF tags (so they survive the file being copied/renamed on its own);
    `write_attribution_sidecar()` writes the same information, more verbosely, to a human-readable
    `<output>_licenza.txt` next to it. Both the Processing algorithm and
    [scripts/export_tiled.py](scripts/export_tiled.py) call both after `merge_tiles()`.
- [tiled_export_algorithm.py](tiled_export_algorithm.py) — `TiledExportAlgorithm`, a
  `QgsProcessingAlgorithm` wrapping `services.export_tiles()`/`merge_tiles()` with the standard
  Processing parameter form (year or custom URL, extent — including "use canvas extent", pixel
  size, advanced tiling knobs, output GeoTIFF). Refuses to run below
  `services.EMPIRICAL_MIN_PIXEL_SIZE` unless the advanced "Forza comunque" boolean is set, rather
  than silently producing an empty file. Progress is only an estimate (the empty-retry tiling depth
  isn't known upfront), nudged up whenever an unplanned retry-split happens. After merging, writes
  the CC BY 4.0 attribution sidecar/TIFF-tags described above and reports the sidecar's path via
  `feedback.pushInfo()`.
- [provider.py](provider.py) — `AgeaOrtofotoProvider`, the `QgsProcessingProvider` that registers
  `TiledExportAlgorithm`. Instantiated once in `AgeaOrtofoto.__init__` and
  added/removed from `QgsApplication.processingRegistry()` in `initGui()`/`unload()` — a provider
  left registered after `unload()` would keep showing the algorithm (pointing at a dead module)
  after the plugin is disabled/updated.
- [metadata.txt](metadata.txt) — standard QGIS plugin metadata (name, version, min QGIS version,
  tags, changelog). Bump `version` and add a `changelog` entry when releasing changes.
  `hasProcessingProvider=yes` must stay in sync with whether `provider.py` actually registers
  something — the Plugin Manager reads it to decide whether to show a Processing entry at all.
- [scripts/export_tiled.py](scripts/export_tiled.py) — a standalone CLI wrapper around the same
  `services.export_tiles()`/`merge_tiles()` used by `TiledExportAlgorithm`, for running the export
  outside QGIS Desktop (e.g. via the qgis-headless skill on WSL2/Linux). Not imported by the plugin
  itself — see Development below for how it's kept out of plugin zips.

## Development

There is no build step, test suite, or linter configured in this repo — it's a plain PyQGIS
plugin loaded directly by QGIS from its plugin directory (or as a zip via the Plugin Manager).
[scripts/](scripts/) is a dev-only CLI utility (not imported by the plugin — see its own
Architecture entry above) excluded from plugin zips via [.gitattributes](.gitattributes)
(`export-ignore`), which only takes effect on `git archive` output (GitHub's "Download ZIP" and
auto-generated release archives) — a zip built by literally running `zip` over the working
directory would still include it.

To test changes, symlink or copy this directory into the QGIS profile's `python/plugins/`
folder, then use the "Plugin Reloader" QGIS plugin (or restart QGIS) to pick up edits.
