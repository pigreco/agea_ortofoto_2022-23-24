# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A QGIS plugin (`AgEA Ortofoto`) that adds a single toolbar/menu action to load AGEA's Italian
orthophoto ArcGIS ImageServer services (2022, 2023, 2024) into a dedicated, grouped layer tree
entry, using QGIS's native `arcgismapserver` raster provider (no external dependencies).

## Architecture

- [__init__.py](__init__.py) — plugin entry point required by QGIS; `classFactory(iface)`
  instantiates `AgeaOrtofoto` from [main.py](main.py).
- [main.py](main.py) — `AgeaOrtofoto` class: QGIS GUI integration (toolbar/menu action,
  `initGui`/`unload` lifecycle). `run()` calls `services.load_all()` and reports the result via
  `iface.messageBar()`.
- [services.py](services.py) — all the actual logic, independent of GUI wiring:
  - `YEARS` / `BASE_URL` define the three ImageServer endpoints.
  - `build_uri()` builds the `arcgismapserver` provider URI. **Both `layer` and `format` must
    stay empty** — an ImageServer has no numbered sub-layers, and setting an explicit format
    overrides the server's default (`jpgpng`), causing the service to return fully transparent
    images. This is the one non-obvious constraint in the codebase.
  - `load_all()` removes any previous `AGEA 2022-23-24` group (so repeated runs don't stack
    duplicates), then adds the three years as raster layers inside a new group, newest year on
    top and the only one visible by default. Returns `(loaded, failed)` name lists so the caller
    can report partial failures (e.g. a service unreachable) without aborting the others.
- [metadata.txt](metadata.txt) — standard QGIS plugin metadata (name, version, min QGIS version,
  tags, changelog). Bump `version` and add a `changelog` entry when releasing changes.

## Development

There is no build step, test suite, or linter configured in this repo — it's a plain PyQGIS
plugin loaded directly by QGIS from its plugin directory (or as a zip via the Plugin Manager).

To test changes, symlink or copy this directory into the QGIS profile's `python/plugins/`
folder, then use the "Plugin Reloader" QGIS plugin (or restart QGIS) to pick up edits.
