# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A QGIS plugin (`AgEA Ortofoto`) that loads AGEA's Italian orthophoto ArcGIS ImageServer services
(2022, 2023, 2024) into a dedicated, grouped layer tree entry, using QGIS's native
`arcgismapserver` raster provider (no external dependencies). A single toolbar/menu action opens
a region-picker dialog that either loads all three years at once ("all regions", the default
selection) or just the single year covering a chosen Italian region, zooming the canvas to it.

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
- [metadata.txt](metadata.txt) — standard QGIS plugin metadata (name, version, min QGIS version,
  tags, changelog). Bump `version` and add a `changelog` entry when releasing changes.

## Development

There is no build step, test suite, or linter configured in this repo — it's a plain PyQGIS
plugin loaded directly by QGIS from its plugin directory (or as a zip via the Plugin Manager).

To test changes, symlink or copy this directory into the QGIS profile's `python/plugins/`
folder, then use the "Plugin Reloader" QGIS plugin (or restart QGIS) to pick up edits.
