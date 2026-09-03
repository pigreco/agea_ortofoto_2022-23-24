# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A QGIS plugin (`AgEA Ortofoto`) that loads AGEA's Italian orthophoto ArcGIS ImageServer services
(2022, 2023, 2024) into a dedicated, grouped layer tree entry, using QGIS's native
`arcgismapserver` raster provider (no external dependencies). Two entry points: a one-click
toolbar/menu action that loads all three years at once, and a region-picker dialog that loads
only the single year covering a chosen Italian region.

## Architecture

- [__init__.py](__init__.py) — plugin entry point required by QGIS; `classFactory(iface)`
  instantiates `AgeaOrtofoto` from [main.py](main.py).
- [main.py](main.py) — `AgeaOrtofoto` class: QGIS GUI integration (toolbar/menu actions,
  `initGui`/`unload` lifecycle). `run()` calls `services.load_all()` (the one-click "load
  everything" action) and reports the result via `iface.messageBar()`. `show_region_dialog()`
  lazily creates and shows the [region_dialog.py](region_dialog.py) `RegionDialog`, wiring its
  `load_requested` signal to `_on_region_load_requested()`, which calls `services.load_year()`
  for the region's year (or delegates to `run()` when "all regions" is chosen).
- [region_dialog.py](region_dialog.py) — `RegionDialog`, a small non-modal `QDialog` with a combo
  box listing every region (from `services.ALL_REGIONS`, each annotated with its year) plus an
  "all regions" entry. Emits `load_requested(region_or_None)` on its "Carica" button instead of
  closing, so the user can load several regions/years in a row without reopening it.
- [services.py](services.py) — all the actual logic, independent of GUI wiring:
  - `YEARS` / `BASE_URL` define the three ImageServer endpoints.
  - `REGIONS_BY_YEAR` / `YEAR_BY_REGION` / `ALL_REGIONS` map each of the 20 Italian regions to the
    single year whose ImageServer covers it (AGEA reshoots a different subset of the country each
    year; see the coverage table in [README.md](README.md)).
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
