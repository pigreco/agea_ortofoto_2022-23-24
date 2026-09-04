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
            '<p>Esporta un ritaglio di un ImageServer AgEA alla dimensione pixel scelta, '
            'tassellando ed eventualmente riprovando in modo automatico dove necessario, poi '
            'unisce tutto in un unico GeoTIFF compresso.</p>'
            '<p><b>Limite del servizio:</b> sotto ~{floor} m/pixel il servizio non restituisce '
            'mai dati, a qualunque dimensione di richiesta - verificato anche su ritagli di '
            'pochi metri, non e\' un problema risolvibile tassellando. Sotto questa soglia '
            'l\'algoritmo si ferma con un errore, a meno di attivare "Forza comunque".</p>'
            '<h3>Parametri</h3>'
            '<p><b>Anno AgEA:</b> quale dei tre servizi ImageServer AgEA interrogare (2022, '
            '2023 o 2024) - ogni anno copre un sottoinsieme diverso di regioni italiane. '
            'Ignorato se e\' compilato "URL ImageServer personalizzato".</p>'
            '<p><b>URL ImageServer personalizzato:</b> avanzato, opzionale. Se impostato, '
            'sostituisce "Anno" e interroga questo ImageServer ArcGIS al posto di uno dei tre '
            'servizi AgEA (ad es. per riusare lo stesso algoritmo su un altro servizio).</p>'
            '<p><b>Estensione da esportare:</b> il rettangolo da ritagliare. Il widget standard '
            'di QGIS permette di digitare le coordinate a mano, usare l\'estensione corrente '
            'della mappa, quella di un layer del progetto, o disegnarla sulla mappa.</p>'
            '<p><b>Dimensione pixel (metri):</b> la risoluzione di output desiderata, in metri '
            '(unita\' della CRS del servizio, EPSG:3857). Deve essere almeno {floor}, salvo '
            'attivare "Forza comunque".</p>'
            '<p><b>Forza comunque sotto {floor} m/pixel:</b> avanzato. Bypassa il controllo di '
            'sicurezza sulla soglia minima. Con uno dei tre servizi AgEA il risultato sara\' '
            'quasi certamente vuoto (e\' un limite verificato del servizio, non un\'ipotesi '
            'prudenziale); serve solo per un "URL ImageServer personalizzato" che potrebbe non '
            'avere questo limite, o per riverificare la soglia nel tempo.</p>'
            '<p><b>Limite pixel per tassello:</b> avanzato. Soglia in numero totale di pixel '
            '(larghezza per altezza) oltre la quale una richiesta viene suddivisa in 4 prima '
            'ancora di essere tentata, solo per contenere memoria e tempi di download - non e\' '
            'un limite imposto dal server (richieste anche di 1 miliardo di pixel sono state '
            'verificate funzionanti in un colpo solo).</p>'
            '<p><b>Lato minimo (px) oltre cui un tassello vuoto e\' considerato area non '
            'coperta:</b> avanzato. Quando un tassello risulta vuoto, l\'algoritmo lo suddivide '
            'in 4 e riprova; sotto questa dimensione smette di insistere e tratta quell\'area '
            'come realmente priva di copertura (bordo della zona sorvolata, mare, ecc.), '
            'escludendola dal mosaico finale invece di lasciarla vuota.</p>'
            '<p><b>Numero massimo di suddivisioni per un tassello vuoto:</b> avanzato. Quante '
            'volte al massimo un ramo puo\' essere suddiviso in 4 solo perche\' e\' tornato '
            'vuoto (indipendentemente dal "Lato minimo") - evita che una grande area '
            'realmente non coperta venga sondata in modo esaustivo fino al singolo pixel.</p>'
            '<p><b>GeoTIFF di output:</b> il percorso del file finale, gia\' unito e compresso '
            '(DEFLATE), dove salvare il ritaglio.</p>'
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
