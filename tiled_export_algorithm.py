# -*- coding: utf-8 -*-
"""Processing algorithm: high-resolution clip export via tiling.

See services.py's "High-resolution tiled export" section for why this
exists - in short, a single request to an AgEA ImageServer silently comes
back blank below ~0.4 m/pixel regardless of size, and real coverage edges
need to be told apart from that. This algorithm exposes services.export_tiles
/ merge_tiles through the standard Processing parameter form, so extent,
pixel size and output all get QGIS's native widgets (including "use canvas
extent"), plus a progress bar and a Cancel button for free.
"""
import os
import shutil
import tempfile

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum,
    QgsProcessingParameterExtent,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterString,
)
from qgis.PyQt.QtCore import QCoreApplication

from .services import (
    BASE_URL,
    DEFAULT_MAX_EMPTY_SPLITS,
    DEFAULT_MAX_TILE_PIXELS,
    DEFAULT_MIN_TILE_PX,
    EMPIRICAL_MIN_PIXEL_SIZE,
    YEARS,
    build_export_layer,
    export_tiles,
    merge_tiles,
    transform_extent,
)


class TiledExportAlgorithm(QgsProcessingAlgorithm):

    YEAR = 'YEAR'
    URL = 'URL'
    EXTENT = 'EXTENT'
    PIXEL_SIZE = 'PIXEL_SIZE'
    FORCE = 'FORCE'
    MAX_TILE_PIXELS = 'MAX_TILE_PIXELS'
    MIN_TILE_PX = 'MIN_TILE_PX'
    MAX_EMPTY_SPLITS = 'MAX_EMPTY_SPLITS'
    OUTPUT = 'OUTPUT'

    def tr(self, text):
        return QCoreApplication.translate('TiledExportAlgorithm', text)

    def createInstance(self):
        return TiledExportAlgorithm()

    def name(self):
        return 'export_ritaglio_alta_risoluzione'

    def displayName(self):
        return self.tr('Esporta ritaglio ad alta risoluzione')

    def group(self):
        return self.tr('AgEA Ortofoto')

    def groupId(self):
        return 'agea_ortofoto'

    def shortHelpString(self):
        return self.tr(
            'Esporta un ritaglio di un ImageServer AgEA alla dimensione '
            'pixel scelta, tassellando ed eventualmente riprovando in modo '
            'automatico dove necessario, poi unisce tutto in un unico '
            'GeoTIFF.\n\n'
            'Il servizio non restituisce mai dati sotto ~{floor} m/pixel, a '
            'qualunque dimensione di richiesta: e un limite del servizio '
            'stesso (verificato anche su ritagli di pochi metri), non '
            'risolvibile tassellando. Sotto questa soglia l\'algoritmo si '
            'ferma con un errore, a meno di attivare "Forza comunque".'
        ).format(floor=EMPIRICAL_MIN_PIXEL_SIZE)

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterEnum(
            self.YEAR,
            self.tr('Anno AgEA'),
            options=[str(year) for year in YEARS],
            defaultValue=len(YEARS) - 1,  # most recent year
        ))
        url_param = QgsProcessingParameterString(
            self.URL,
            self.tr('URL ImageServer personalizzato (sostituisce "Anno" se impostato)'),
            optional=True,
        )
        url_param.setFlags(url_param.flags() | QgsProcessingParameterString.FlagAdvanced)
        self.addParameter(url_param)

        self.addParameter(QgsProcessingParameterExtent(
            self.EXTENT,
            self.tr('Estensione da esportare'),
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.PIXEL_SIZE,
            self.tr('Dimensione pixel (metri)'),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=0.5,
            minValue=0.01,
        ))

        force_param = QgsProcessingParameterBoolean(
            self.FORCE,
            self.tr('Forza comunque sotto {floor} m/pixel').format(floor=EMPIRICAL_MIN_PIXEL_SIZE),
            defaultValue=False,
        )
        force_param.setFlags(force_param.flags() | QgsProcessingParameterBoolean.FlagAdvanced)
        self.addParameter(force_param)

        max_px_param = QgsProcessingParameterNumber(
            self.MAX_TILE_PIXELS,
            self.tr('Limite pixel per tassello (solo per contenere memoria/tempi)'),
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=DEFAULT_MAX_TILE_PIXELS,
            minValue=1_000_000,
        )
        max_px_param.setFlags(max_px_param.flags() | QgsProcessingParameterNumber.FlagAdvanced)
        self.addParameter(max_px_param)

        min_px_param = QgsProcessingParameterNumber(
            self.MIN_TILE_PX,
            self.tr('Lato minimo (px) oltre cui un tassello vuoto è considerato area non coperta'),
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=DEFAULT_MIN_TILE_PX,
            minValue=10,
        )
        min_px_param.setFlags(min_px_param.flags() | QgsProcessingParameterNumber.FlagAdvanced)
        self.addParameter(min_px_param)

        empty_splits_param = QgsProcessingParameterNumber(
            self.MAX_EMPTY_SPLITS,
            self.tr('Numero massimo di suddivisioni per un tassello vuoto'),
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=DEFAULT_MAX_EMPTY_SPLITS,
            minValue=0,
        )
        empty_splits_param.setFlags(empty_splits_param.flags() | QgsProcessingParameterNumber.FlagAdvanced)
        self.addParameter(empty_splits_param)

        self.addParameter(QgsProcessingParameterRasterDestination(
            self.OUTPUT,
            self.tr('GeoTIFF di output'),
        ))

    def processAlgorithm(self, parameters, context, feedback):
        year_index = self.parameterAsEnum(parameters, self.YEAR, context)
        url = self.parameterAsString(parameters, self.URL, context).strip()
        if not url:
            url = BASE_URL.format(year=YEARS[year_index])

        pixel_size = self.parameterAsDouble(parameters, self.PIXEL_SIZE, context)
        force = self.parameterAsBoolean(parameters, self.FORCE, context)
        if pixel_size < EMPIRICAL_MIN_PIXEL_SIZE and not force:
            raise QgsProcessingException(
                self.tr(
                    'Dimensione pixel {px} inferiore a {floor} m/pixel: il servizio non '
                    'restituisce dati sotto questa soglia, a qualunque dimensione di '
                    'richiesta (non e\' un problema risolvibile tassellando). Usa {floor} '
                    'o un valore maggiore, oppure attiva "Forza comunque".'
                ).format(px=pixel_size, floor=EMPIRICAL_MIN_PIXEL_SIZE)
            )

        max_tile_pixels = self.parameterAsInt(parameters, self.MAX_TILE_PIXELS, context)
        min_tile_px = self.parameterAsInt(parameters, self.MIN_TILE_PX, context)
        max_empty_splits = self.parameterAsInt(parameters, self.MAX_EMPTY_SPLITS, context)
        output_path = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)

        extent_crs = self.parameterAsExtentCrs(parameters, self.EXTENT, context)
        if not extent_crs.isValid():
            extent_crs = QgsCoordinateReferenceSystem('EPSG:4326')
        extent = self.parameterAsExtent(parameters, self.EXTENT, context, extent_crs)

        feedback.pushInfo(self.tr('Apertura del servizio: {url}').format(url=url))
        try:
            layer = build_export_layer(url)
        except RuntimeError as exc:
            raise QgsProcessingException(str(exc))

        extent = transform_extent(extent, extent_crs, layer.crs(), context.project())
        feedback.pushInfo(
            self.tr('Estensione: {ext} ({crs})').format(ext=extent.toString(2), crs=layer.crs().authid())
        )

        # Progress is estimated from the budget-forced quadtree depth alone
        # (ignoring empty-retry splits, unknown in advance) and nudged up
        # whenever those extra splits happen, so it stays informative
        # without pretending to be exact.
        planned = [_estimate_tile_count(extent, pixel_size, max_tile_pixels)]
        done = [0]

        def on_tile(event, **info):
            if event == 'exported':
                done[0] += 1
                feedback.setProgress(min(99, int(100 * done[0] / max(planned[0], 1))))
                feedback.pushInfo(
                    self.tr('Tassello {n}: {w}x{h} px OK').format(
                        n=done[0], w=info['width'], h=info['height'])
                )
            elif event == 'empty':
                planned[0] += 3  # this branch just turned into 4 sub-attempts
                feedback.pushInfo(
                    self.tr('Area {ext} vuota a {w}x{h} px, suddivido e riprovo...').format(
                        ext=info['extent'].toString(1), w=info['width'], h=info['height'])
                )
            elif event == 'skipped':
                feedback.pushInfo(
                    self.tr('Area {ext} non coperta dal servizio, esclusa dal mosaico.').format(
                        ext=info['extent'].toString(1))
                )

        work_dir = tempfile.mkdtemp(prefix='agea_export_tiles_')
        try:
            tiles = export_tiles(
                layer, layer.crs(), extent, pixel_size, work_dir,
                max_tile_pixels=max_tile_pixels,
                min_tile_px=min_tile_px,
                max_empty_splits=max_empty_splits,
                on_tile=on_tile,
                should_cancel=feedback.isCanceled,
            )

            if feedback.isCanceled():
                raise QgsProcessingException(self.tr('Annullato dall\'utente.'))

            if not tiles:
                raise QgsProcessingException(
                    self.tr('Nessun dato valido nell\'area richiesta: il servizio non copre '
                            'questa zona (o non a questa dimensione pixel).')
                )

            feedback.pushInfo(self.tr('Unione di {n} tassello/i in corso...').format(n=len(tiles)))
            merge_tiles(tiles, output_path)
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

        feedback.setProgress(100)
        return {self.OUTPUT: output_path}


def _estimate_tile_count(extent, pixel_size, max_tile_pixels):
    width = max(1, round(extent.width() / pixel_size))
    height = max(1, round(extent.height() / pixel_size))
    total = width * height
    count = 1
    while total > max_tile_pixels:
        total /= 4
        count *= 4
    return count
