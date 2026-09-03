# AgEA Ortofoto 2022-23-24

Plugin QGIS per caricare con un click le ortofoto AGEA 2022, 2023 e 2024 in un
gruppo dedicato del progetto.

## Cosa fa

Aggiunge un pulsante in barra degli strumenti (e una voce nel menu Web) che
apre una finestra di selezione per caricare i servizi ArcGIS ImageServer
delle Ortofoto AgEA pubblicati sul
[Geoportale AgEA](https://geoportale.agea.gov.it) - tutti e tre gli anni
insieme, oppure solo quello di una singola regione - organizzandoli in un
gruppo **"AGEA 2022-23-24"** con il 2024 in cima, unico anno visibile
all'avvio. Se il gruppo esiste gia' viene ricreato (o aggiornato), cosi' i
lanci successivi non accumulano layer duplicati.

Non ha dipendenze esterne: usa il provider `arcgismapserver` nativo di QGIS.

## Requisiti

- QGIS >= 3.20 (compatibile anche con QGIS 4.x / Qt6)
- Connessione internet (i dati sono serviti in streaming da AGEA, nessun
  download locale)

## Installazione

1. Scarica o clona questo repository.
2. Copia la cartella nella directory dei plugin di QGIS, ad esempio:
   - Linux: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
   - Windows: `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`
3. Attiva il plugin da **Plugin > Gestisci e installa plugin**.

## Utilizzo

Clicca l'icona **"Carica Ortofoto AgEA"** in barra degli strumenti (o la voce
di menu): si apre una finestra con un menu a tendina che elenca tutte le
regioni italiane (ciascuna etichettata con l'anno che la copre) piu' una voce
**"Tutte le regioni"**, selezionata di default. Premi **"Carica"** per:

- caricare tutti e tre gli anni in un click, lasciando selezionata "Tutte le
  regioni"; oppure
- caricare solo il servizio dell'anno che copre una regione scelta (il
  servizio copre comunque l'intera area ripresa quell'anno, non solo la
  regione selezionata) - la mappa si zooma automaticamente sulla sua
  estensione.

La finestra resta aperta per caricare piu' regioni/anni di seguito senza
doverla riaprire; il canvas di QGIS torna comunque in primo piano dopo ogni
caricamento, cosi' il risultato e' visibile subito.

Per vedere le immagini e' necessario zoomare oltre la scala 1:50.000: a scale
piu' basse gli ImageServer non restituiscono contenuto.

## Copertura per anno

Ogni servizio copre un sottoinsieme diverso di regioni italiane, a rotazione
sul triennio (dato ricavato dai valori distinti del campo `regione` nei
footprint dei mosaic dataset):

| Anno | Regioni coperte | N. |
|---|---|---|
| **2022** | Abruzzo, Liguria, Marche, Puglia, Sardegna, Sicilia, Toscana | 7 |
| **2023** | Basilicata, Campania, Emilia-Romagna, Friuli-Venezia Giulia, Lazio, Trentino-Alto Adige, Umbria | 7 |
| **2024** | Calabria, Lombardia, Molise, Piemonte, Valle d'Aosta, Veneto | 6 |

## Note tecniche

Le richieste agli ImageServer vanno fatte con i parametri `layer` e `format`
vuoti: valorizzarli fa restituire al server immagini completamente
trasparenti, perche' un ImageServer non ha sotto-layer numerati e un formato
esplicito sovrascrive quello di default (`jpgpng`), l'unico che gestisce
correttamente il nodata.

## Licenza

Codice distribuito con licenza [GPL v2](LICENSE) (o successiva).
I dati delle ortofoto sono pubblicati da AGEA in licenza CC BY 4.0.

## Ringraziamenti

- [Andrea Borruso](https://github.com/aborruso) per l'idea
- [AGEA](https://geoportale.agea.gov.it/) per aver condiviso i dati in CC BY 4.0
