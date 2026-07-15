# Updates

Laufendes Änderungsprotokoll für dieses Projekt (Fork von [route-tiles](https://github.com/BenoitBouillard/route-tiles)). Neue Einträge werden **oben** ergänzt. Für die Begründung *warum* etwas so gebaut ist, siehe `DOCUMENTATION.md`.

---

## Kachel-Darstellung an squadrats.com angleichen (TODO Nr. 1)

Vom Nutzer außerhalb dieser Session umgesetzt (keine Code-Änderung innerhalb dieser Sitzung, daher hier ohne technisches Detail dokumentiert).

---

## Bugfix: Cluster-Umriss auf der Karte kaum erkennbar

- **Symptom:** die Umrandung des zusammenhängenden Kachel-Clusters war auf der Karte schlecht zu erkennen.
- **Ursache:** die Umrandung war grün (`#20ff2080`, halbtransparent) – exakt dieselbe Farbfamilie wie die Füllfarbe der besuchten Kacheln (`green`), deren Rand sie ja gerade nachzeichnet. Beides verschmilzt optisch ineinander.
- **Fix** (`static/index.js`, `static/index.html`): auf ein kräftiges, voll deckendes Orange (`#FF8C00`) umgestellt – klar unterscheidbar sowohl von der grünen Kachel-Füllung als auch vom roten Kachel-Gitter. Legenden-Farbmuster entsprechend mitgezogen.
- **Verifiziert:** mit den Demo-Daten (siehe unten) auf die Karte gezoomt und per Screenshot geprüft – die Umrandung ist jetzt deutlich als eigene Linie erkennbar, statt im grünen Kachel-Hintergrund unterzugehen.

---

## Feature: Demo-Modus (TODO Nr. 2)

- **Bundled Beispieldaten** (`demo_data/activities_1.json`): synthetischer, aber realistisch geformter Kachel-Datensatz (45 Kacheln) im echten Statshunters-Aktivitäten-Schema – ein solider 6×6-Block ("Ride", ergibt ein echtes 6×6-Max-Quadrat mit sinnvoller "nächste Quadratgröße"-Empfehlung), eine unregelmäßige Erweiterung sowie ein separater, unverbundener 2×2-Block ("Run", zum Vorführen des Aktivitätstyp-Filters und der Mehr-Zonen-Behandlung). Bewusst außerhalb von `data/` (das ist – gitignored – für echte Nutzer-Imports reserviert), damit die Demo-Daten tatsächlich mit dem Repo ausgeliefert werden.
- **Server** (`route-tiles-server.py`): neue `_activities_folder()`-Hilfsmethode löst `demo=1` **vor** jeder URL-Betrachtung auf und liefert direkt den gebündelten Demo-Ordner – berührt den `url`-Parameter und damit auch die kürzlich gehärtete SSRF-/Verzeichnis-Escape-Validierung (siehe TODO-Nr.-3-Eintrag) überhaupt nicht. Alle vier betroffenen Endpunkte (`/statshunters`, `/statshunters_filter`, `/scoring`, `/start_orienteering`) nutzen diese Hilfsmethode jetzt einheitlich.
- **Frontend** (`static/index.js`/`index.html`): ein echter An/Aus-Schalter (Bootstrap Custom-Switch `#bDemoModeToggle`, nicht nur ein einmaliger Button) oben auf der Seite direkt unter der Sprachauswahl - unabhängig vom "Kartendaten"-Panel, damit er unabhängig von dessen Auf-/Zuklappzustand sichtbar bleibt. Ein `demoMode`-Flag route­t alle Statshunters-/Scoring-/Orienteering-Anfragen über `demo=1` statt `url=...` (neue `getStatshuntersParams()`-Hilfsfunktion, ersetzt die bisherigen verstreuten `{url: ...}`-Inline-Objekte) und überspringt die client-seitige URL-Validierung; das URL-Feld wird währenddessen deaktiviert. Ausschalten stellt den zuvor gespeicherten echten Statshunters-Link (falls vorhanden) wieder her, statt ihn zu löschen - die neue `clearStatshuntersData()`-Hilfsfunktion bündelt die gemeinsame Aufräumlogik, die sich vorher nur im "Zurücksetzen"-Button befand. Der "Zurücksetzen"-Button deaktiviert den Schalter mit, falls Demo-Modus gerade aktiv war.
- **Verifiziert:** alle vier Endpunkte direkt mit `demo=1` gegen den laufenden Server getestet (liefern die erwarteten 45 Kacheln, Aktivitätstyp-Filter, Max-Quadrat-/Cluster-KML, Quadrat-Vervollständigungs-Vorschlag); echter Statshunters-Link und die SSRF-/Traversal-Abwehr funktionieren unverändert daneben weiter. Kompletter Klick-Flow per Playwright gegen die echte Seite geprüft (Schalter ein → 45 Kacheln geladen, Aktivitätstyp-Dropdown zeigt Ride/Run, Quadrat-Vervollständigungs-Hinweis erscheint korrekt, URL-Feld gesperrt; Schalter aus → alles sauber zurückgesetzt, URL-Feld wieder frei; "Zurücksetzen" bei aktivem Demo-Modus schaltet auch den Switch ab), keine JavaScript-Fehler, Screenshot zeigt die Platzierung neben der Sprachauswahl korrekt gerendert.

---

## TODO Nr. 3 abgearbeitet: Sicherheitsaudit, Orienteering-Abbruch-Test, Testsuite, Performance-Analyse

### Sicherheit

- **SSRF + Verzeichnis-Escape über den `url`-Parameter behoben** (`statshunters.py`): `_normalize_share_url()` akzeptierte bei einem nicht passenden Muster bisher stillschweigend die rohe, unvalidierte Eingabe als Fallback. Das erlaubte zwei echte Angriffe über denselben `url`-Query-Parameter (an `/statshunters`, `/statshunters_filter`, `/scoring`, `/start_orienteering`): (1) **SSRF** – eine beliebige Host/Port-Kombination (z. B. `http://169.254.169.254/share/x` oder ein internes Netzwerkziel) wurde anstandslos angefragt, da die alte Regex `[^/]+` als Host akzeptierte; (2) **Verzeichnis-Escape** – bei einer Eingabe ohne weiteren Schrägstrich (z. B. exakt `..`) wurde `index = sharelink_url.split('/')[-1]` zu `".."`, wodurch `Path(folder).joinpath(index)` eine Ebene über dem `data/`-Cache-Ordner landete (verifiziert: löst sich zum Projekt-Root auf). Fix: `_normalize_share_url()` verlangt jetzt zwingend `https?://(www.)?statshunters.com/share/<alphanumerisch>` und wirft andernfalls `ValueError`, statt einen unsicheren Fallback zu nutzen; `statshunters_path()` leitet die Cache-Verzeichnis-ID zusätzlich aus der bereits validierten ID her (nicht mehr aus dem rohen String), als zweite Verteidigungslinie. Alle vier Endpunkte in `route-tiles-server.py` fangen den `ValueError` jetzt sauber ab (JSON-`Fail`-Antwort statt rohem Stacktrace).
- **Toter, aber gefährlicher Code entfernt** (`route-tiles-server.py`): `deal_post_data()` (nie aufgerufen, siehe Grep über den ganzen Code) baute einen Dateipfad direkt aus dem `filename`-Feld eines Multipart-Uploads (`Content-Disposition`-Header) zusammen – komplett ungeprüft, kein Schutz vor `../../`-Traversal oder absoluten Pfaden. Da nie erreichbar, kein aktiv ausnutzbares Loch, aber ein Fund, der bei einer künftigen, gedankenlosen Anbindung sofort zu einem waschechten "beliebige Datei schreiben"-Bug geworden wäre – ersatzlos gestrichen.
- **Session-IDs auf CSPRNG umgestellt**: `generate_random()` nutzte `random.choice()` (Mersenne-Twister, bei genug beobachteter Ausgabe vorhersagbar) für Session-IDs, die als unauthentifiziertes Bearer-Token fungieren (wer die ID kennt, kann die laufende Streckensuche dieser Session lesen/abbrechen). Umgestellt auf `secrets.choice()`.
- **Bereits vorhandene, geprüfte Punkte ohne Fund:** kein `eval`/`exec`/`pickle`/`subprocess`/Shell-Aufruf im gesamten Code (das einzige `eval()` war die bereits in einer früheren Sitzung behobene Aktivitätsfilter-Lücke); GPX-Erzeugung nutzt `gpxpy`s eigenes, escapendes API statt String-Konkatenation (keine XML-Injection); statische Dateiauslieferung korrekt auf `static/` beschränkt (`SimpleHTTPRequestHandler`s eigener Traversal-Schutz); keine CORS-Header gesetzt (Same-Origin-Policy bleibt intakt); Dateinamen-Felder für GPX-/KML-Generierung blocken bereits `/`/`\` vollständig, was Traversal dort schon ausschließt.
- **Verifiziert:** SSRF- und Traversal-Payloads (`url=..`, `url=http://169.254.169.254/share/x`) direkt gegen den laufenden Server getestet – beide liefern jetzt eine saubere `{"status": "Fail", ...}`-Antwort statt eines Angriffs bzw. eines rohen Stacktraces; der reguläre Statshunters-Import mit einem echten Share-Link funktioniert unverändert. Regressionstests für beide Fälle in `tests/test_statshunters.py` festgehalten.

### Orienteering-Abbruch-Test (letzter offener Punkt aus TODO Nr. 3)

- Mit echten, gecachten Statshunters-Daten (`data/abcdef123456`, 2389 Kacheln) eine echte Streckenvorgabe-Suche gestartet, nach 3 Sekunden abgebrochen und bis zum tatsächlichen Suchende (146,6 Sekunden) durchgehend beobachtet. Verhält sich exakt wie der bereits verifizierte manuelle/OR-Tools-Pfad: der Abbruch kann den laufenden, blockierenden OR-Tools-Aufruf nicht mitten drin unterbrechen (dieselbe dokumentierte Einschränkung wie beim manuellen Pfad), aber sobald der Aufruf zurückkehrt, wird das Ergebnis korrekt verworfen (`error_code=2`/`ERR_ABORT_REQUEST`, `route=None`) statt als Erfolg gemeldet. Kein Bug – Verhalten jetzt für beide Suchpfade bestätigt.

### Testsuite (`tests/`, per `pytest` lauffähig)

- Neue Regressionstest-Sammlung (45 Tests, `pytest.ini` setzt `pythonpath = .`, `requirements-dev.txt` für `pytest`): `test_tile.py` (Kachel-Geometrie/-Mathematik), `test_scoring.py` (`compute_zones`, `find_best_square_completion` inkl. Konnektivitäts-Garantie), `test_statshunters.py` (URL-Validierung – direkte Regressionstests für den SSRF/Traversal-Fix oben –, Aktivitäts-Parsing, die schon zuvor behobenen Leere-Kacheln-Abstürze), `test_route_timing.py` (Interpolation/Extrapolation/Historien-Deckelung), `test_ortools_router.py` (der `_cost_graph()`-Luftlinien-Sicherheitsnetz aus der "wilde Sprünge"-Untersuchung, direkt als Regressionstest nachgebildet). Ersetzt die bisherigen Ad-hoc-`curl`/Python-Skripte dieser Sitzung durch etwas, das jederzeit erneut mit `pytest` laufen kann.

### Performance-Analyse (echte Messungen, keine Schätzung)

- **Reine Berechnungsfunktionen sind kein Thema:** `tiles_from_activities`, `compute_max_square`, `compute_cluster`, `find_best_square_completion` brauchen mit den echten 2389 Kacheln allesamt <25 ms.
- **OR-Tools-Solver skaliert vorhersagbar:** aus der über diese Sitzung real akkumulierten Zeitmess-Historie (`route_timing_history.json`) – ziemlich exakt ~1 Sekunde pro Kachel im Bereich 27–35 Kacheln (z. B. 29 Kacheln → 29,7 s, 35 Kacheln → 36,2 s). Ein Ausreißer (58 Kacheln in nur 10,6 s statt der sonst beobachteten ~54 s) deutet auf Kachel-Anordnung/Dichte als weiteren Faktor neben der reinen Anzahl hin.
- **Konkreter Befund – exakter Solver ist NICHT primär eine Funktion der Kachelanzahl:** dieselbe Historie zeigt für den exakten Algorithmus (`do_route_with_crossing_zone`) eine 2-Kacheln-Suche mit 125,3 Sekunden – langsamer als so gut wie jede gemessene 30-Kacheln-OR-Tools-Suche – während zwei 4-Kacheln-Suchen nur 2,5 s brauchten. Direkt nachgemessen (echte Munich-Kachel `8700_5661`, 22 Eintrittsknoten vs. `8707_5659`, 0 Eintrittsknoten in derselben Region): `get_entry_points()` selbst ist mit 39 ms pro Kachel kein Thema, aber der exakte Algorithmus durchsucht laut eigenem Docstring *jede Eintrittspunkt-Kombination* pro Zone kombinatorisch – bei zwei entry-point-dichten Kacheln (20-40 Eintrittspunkte statt 2-5) explodiert der Suchraum unabhängig von der Kachelanzahl. Die Zeitschätzungs-Funktion (`route_timing.py`) korreliert aktuell nur mit der Kachelanzahl und kann für den exakten Pfad deshalb systematisch daneben liegen – als konkreter Verbesserungskandidat für `route_timing.py` festgehalten (z. B. zusätzlich die Summe der Eintrittspunkte pro Suche mit aufzeichnen).
- **OSM-Gebiets-Download ist der mit Abstand größte Hebel, bereits behoben:** eine noch nie gecachte Gegend brauchte real >2 Minuten für den Overpass-Download (vs. <1 ms für einen Cache-Hit derselben Gegend) – der eigentliche, in dieser Sitzung bereits behobene Bug (siehe "Kacheln fürs größte Quadrat"-Eintrag) war, dass dieser Download synchron vor dem Hintergrund-Thread lief. Die Downloadzeit selbst (Overpass-API-Antwortzeit) bleibt ein externer Faktor, der sich nur durch kleinere/gezieltere Downloads statt eines großen kombinierten Bounding-Box-Downloads weiter drücken ließe – als mögliche zukünftige Optimierung notiert, nicht umgesetzt (größerer, eigenständiger Umbau von `preload_region()`).
- **Nebenbei bereinigt:** zwei künstliche Testwerte, die während der Zeitschätzungs-Untersuchung versehentlich in `route_timing_history.json` gelandet waren, entfernt – die Datei enthält jetzt nur noch echte Messungen.

---

## Modernisierungs-Audit (TODO Nr. 4) abgearbeitet

- **`pyroutelib3.py` auf Gewichtstabellen reduziert** (535 → ~80 Zeilen): der komplette alte OSM-Parsing-/Live-Download-/`Datastore`-Code war seit der `osmnx`-Migration toter Code (verifiziert: nur `TYPES` wird noch irgendwo importiert, siehe `osmnx_datastore.py`). Entfernt: `Datastore`-Klasse, `_which_tile`/`_tile_boundary`/`myurlretrieve`/`attributes`/`equivalent`, ungenutzte Imports. `TYPES` samt der beiden Gewichtsfunktionen (`weight_primary_roadcycle`, `filter_asphalt`) unverändert erhalten.
- **`not_update_routing`-Buchführung entfernt** (`tile.py`, `osmnx_datastore.py`): war fürs alte, lazy-ladende `pyroutelib3.Datastore`-Modell gedacht (verhindert doppeltes Verarbeiten bei wiederholtem Nachladen); verifiziert, dass seit der `osmnx`-Migration niemand diesen Dict mehr liest (nur noch geschrieben) – mit der `pyroutelib3.Datastore`-Entfernung endgültig tot.
- **`fastkml` von `<1.0` (installiert: 0.12) auf 1.4.x portiert**: die alte, imperative API (`k.append(d)`, `p.geometry = geom` nach Konstruktion, `Placemark(ns, tileId, styleUrl="#s")`) durch die aktuelle, deklarative API ersetzt (`features=[...]`-Listen im Konstruktor, `geometry=`/`style_url=`-Keyword-Argumente). Betroffen: `statshunters.py`s `getKmlFromGeom()` (Basis für die Max-Square/Cluster-KML-Overlays auf der Karte) und `tile.py`s `tiles_to_kml()` (KML-Tile-Export). Dabei eine bedeutungslose, leere verschachtelte Folder-Struktur aus dem Original entfernt (trug nie zum Ergebnis bei). Der `.replace('kml:', '')`-Kniff in `getKmlFromGeom()` bewusst beibehalten – auch mit `ns=''` emittiert `fastkml` bei Polygon/LinearRing-Geometrie weiterhin `kml:`-präfigierte Kindelemente, und `leaflet-omnivore`s KML-Parser sucht Elemente ohne Namespace-Bewusstsein rein nach Tag-Namen.
- **Frontend-Abhängigkeiten auf die neuesten rückwärtskompatiblen Versionen gehoben** (CDN-Links + SRI-Hashes in `index.html`): jQuery 3.4.1→3.7.1, Leaflet 1.6.0→1.9.4, Bootstrap 4.5.2→4.6.2 (letzte 4.x-Version, von stackpath- auf cdnjs-CDN umgezogen da stackpath keine 4.6.2 mehr hostet), jquery.i18n 1.0.7→1.0.9, popper.js 1.16.0→1.16.1. Bootstrap 5 (Major-Upgrade mit Breaking Changes) und der leaflet-omnivore-Ersatz bleiben auf Nutzerentscheidung hin bewusst zurückgestellt, siehe `TODO.md`.
- **`do_route_with_crossing_zone`** (exakter Algorithmus): strukturell geprüft, mit erklärendem Docstring versehen (A*-artige Suche über (Knoten, Restzonen)-Zustände, Heuristik-Herleitung). Bewusst nicht umgeschrieben – kein konkreter Bug, nur "strukturell dicht", und ein Umbau ohne treibenden Anlass wäre unnötiges Regressionsrisiko für eine mehrfach in dieser Sitzung real verifizierte, korrekt funktionierende Suche.
- **Verifiziert:** nach jeder Änderung eigenständig real getestet – `pyroutelib3`/`osmnx_datastore`-Imports funktionieren weiter; echte Route-Suche mit dem exakten Solver erfolgreich (21,28 km); `/statshunters`-Endpunkt liefert wieder valides Max-Square- und Cluster-KML (mit echten, gecachten Statshunters-Daten, 2389 Kacheln); `/generate_kml_tiles`-Endpunkt liefert valides, korrekt benanntes Tile-KML; Frontend nach dem Versions-Update per Playwright geprüft (jQuery 3.7.1/Leaflet 1.9.4/Bootstrap 4.6.2/jquery.i18n korrekt geladen, Modal öffnet/schließt weiterhin korrekt, keine JavaScript-Fehler, Screenshot zeigt unveränderte, korrekt gerenderte Oberfläche). `requirements.txt` entsprechend aktualisiert (`fastkml>=1.0`).

---

## Bugfix: Streckensuche für die "Kacheln fürs größte Quadrat"-Empfehlung "funktioniert nicht"

- **Symptom:** wählt man genau die lila hervorgehobenen Kacheln aus (die Empfehlung, mit welchen Kacheln sich das größte Quadrat vergrößern lässt) und klickt "Route planen", scheint die Suche einfach nicht zu funktionieren.
- **Ursache gefunden – kein Absturz, sondern eine unsichtbare, teils minutenlange Blockade:** diese Kacheln werden rein nach Gitter-Geometrie ausgewählt (kleinste zusammenhängende Lücke fürs nächstgrößere Quadrat) – sie liegen praktisch immer in einer Gegend, die man noch nie befahren *und* noch nie durchsucht hat. Für so eine Gegend muss `osmnx` die Straßendaten erst per Overpass-API aus dem Netz laden (`preload_region()` → `ox.graph_from_bbox()`), was echt mehrere Minuten dauern kann – real reproduziert: ein Testlauf für eine solche neue Gegend brauchte über 2 Minuten allein fürs Laden, ein zweiter Lauf (Gegend jetzt lokal zwischengespeichert) nur noch 18 Sekunden für dieselbe Suche. Das eigentliche Problem: dieser komplette Download lief bisher *synchron* in `RouteServer.start_route()`, **bevor** der Hintergrund-Thread für die Suche überhaupt gestartet wurde – die `/start_route`-Anfrage selbst (und damit jede Fortschrittsanzeige) blockierte die ganze Downloadzeit über, ohne jede Rückmeldung. Aus Nutzersicht sieht das aus wie eine hängende bzw. kaputte Suche, ist aber ein unsichtbarer, unbegrenzt wirkender Wartevorgang.
- **Fix** (`tilesrouter.py`, `RouteServer.start_route()`): der komplette Vorbereitungsblock (Gebiets-Download, Auflösung von Start/Ziel/Wegpunkten zu echten Knoten, Aufbau von `MyRouter`) läuft jetzt selbst im Hintergrund-Thread, nicht mehr davor. Eine leichte Platzhalter-Klasse `_PendingRoute` (dasselbe Duck-Typing-Prinzip wie schon bei `OrienteeringRunner`) steht für `self.myRouter`, bis der Hintergrund-Thread so weit ist – `/route_status`-Polling zeigt in der Zwischenzeit korrekt "searching" statt eines Fehlers oder eines hängenden Requests. Ein Sicherheitscheck verhindert, dass ein durch Abbruch+Neustart überholter, noch mitten im (nicht abbrechbaren) Download steckender alter Suchlauf am Ende sein Ergebnis über eine inzwischen neuere Suche schreibt.
- **Verifiziert:** echter Nachbau mit den 5 realen, vom Server gelieferten "Quadrat vergrößern"-Kacheln (`find_best_square_completion()` auf den echten 2389 gecachten Statshunters-Kacheln angewendet) – vorher blockierte `start_route()` >2 Minuten für diese neue Gegend; nachher liefert der Aufruf sofort (<5ms, per echtem HTTP-Request gegen den laufenden Server gemessen) eine "searching"-Antwort zurück, während die eigentliche Suche im Hintergrund weiterläuft und nach Abschluss korrekt eine 18,8-km-Route liefert.

---

## Bugfix: Gravel-Dialog "Erlauben" startet die Suche nicht wirklich neu

- **Symptom:** nach "Gravel für diese Kachel erlauben" im Dialog scheint die Suche sofort wieder mit "Fail: no entry point for the tile" fehlzuschlagen – erst ein manueller, weiterer Klick auf "Route planen" liefert dann eine Route, die Gravel für diese Kachel nutzt.
- **Ursache:** kein Server-, sondern ein Frontend-Bug aus einer früheren Umbauphase dieser Sitzung. `request_route()` wurde damals bewusst zu einer No-op-Funktion gemacht (`function request_route() {}`), um das alte "bei jeder Kleinigkeit automatisch neu suchen"-Verhalten abzuschalten – die Absicht war, dass nur noch der explizite Klick auf "Route planen" wirklich etwas auslöst. Die beiden Gravel-Dialog-Buttons ("Erlauben"/"Kachel entfernen") riefen aber weiterhin `request_route()` auf, in der Annahme, das würde die Suche automatisch neu starten. Tat es aber nicht mehr. Der Dialog aktualisiert `gravel_tiles` also korrekt, startet aber keine neue Suche – die alte Fehlermeldung vom *vorherigen* (noch ohne Gravel gescheiterten) Versuch bleibt einfach stehen, bis der Nutzer selbst nochmal auf "Route planen" klickt (was dann der eigentlich erste echte Versuch mit Gravel ist – und erfolgreich).
- **Fix** (`static/index.js`): `#bPlanRoute`s Klick-Logik in eine benannte Funktion `planRoute()` ausgelagert; beide Gravel-Dialog-Buttons rufen jetzt `planRoute()` statt der wirkungslosen `request_route()` auf, lösen also nach der Nutzerentscheidung wirklich eine neue Suche aus.
- **Verifiziert:** Playwright-Check gegen die echte Seite – `#bPlanRoute` ist an die benannte Funktion `planRoute` gebunden, beide Gravel-Dialog-Handler rufen im Quelltext jetzt nachweislich `planRoute()` auf (vorher `request_route()`), keine JavaScript-Fehler beim Laden.

---

## Bugfix: "wilde Sprünge" – dritte Ursache, diesmal die eigentliche Wurzel (31-Kacheln-Fall, test3.gpx)

- **Wieder aufgetreten, trotz der beiden vorherigen Fixes.** Nutzer meldete den Sprung ein drittes Mal (dritte reale GPX-Datei). Diesmal ließ er sich mit den exakten 31 Kacheln aus `debug/tiles.js` **nicht** isoliert reproduzieren – ein einzelner, frischer Suchlauf mit exakt denselben Kacheln/Start/Ziel war sauber. Der Blick ins Server-Log (`/tmp/server.log`, `pprint(qs)` in `do_GET_start_route`) zeigte den eigentlichen Ablauf: der Nutzer hatte zuerst eine Runde mit denselben 31 Kacheln gestartet (sauber, 66,51 km), dann **innerhalb derselben Browser-Session** Zielpunkt und einen Wegpunkt geändert und mit denselben Kacheln erneut gesucht – erst dieser zweite Request (gleiche Session, gleiche Kacheln, anderes Ziel) erzeugte die falschen `edge_length`-Werte.
- **Ursache gefunden – ein alter, bisher unbemerkter Cache-Bug:** `RouteServer` (tilesrouter.py) hatte von Anfang an ein `self.stored_tiles = {}`, das nur bei Moduswechsel zurückgesetzt wird – offensichtlich als Kachel-Cache über mehrere Suchen einer Session hinweg gedacht. Tatsächlich gelesen/geschrieben wurde aber `MyRouter.stored_tiles` – ein **eigenes, in `MyRouter.__init__` bei jeder einzelnen Suche frisch angelegtes** `{}`, weil jede Suche eine neue `MyRouter`-Instanz erzeugt. `RouteServer.stored_tiles` existierte also nur zum Schein und wurde nie konsultiert. Ergebnis: jede zweite (oder n-te) Suche in derselben Session hat für **jede** Kachel erneut `get_entry_points()` aufgerufen – auf dem bereits von der ersten Suche zerlegten Straßennetz (`router.routing` bleibt über Suchen hinweg erhalten, nur der Modus setzt es zurück). Exakt derselbe Mechanismus wie beim vorherigen Fix (künstliche Knoten-ID beginnt wieder bei 0, kollidiert mit bereits vergebenen IDs, überschreibt `edge_lengths`/`edge_shapes` fremder Punkte) – nur diesmal ausgelöst durch zwei getrennte Suchanfragen statt durch zwei Aufrufe innerhalb einer Suche.
- **Das erklärt auch, warum der vorherige Fix (Runde 2) nicht ausreichte:** der behob nur die Doppel-Berechnung *innerhalb* einer einzelnen Suche (OR-Tools' `_tile_representative_node`); das eigentliche, größere Loch – gar kein funktionierender Cache *zwischen* Suchen – blieb offen, weil es nie als eigener Verdächtiger auffiel (der Name `stored_tiles` suggerierte, dass hier bereits gecacht wird).
- **Fix (strukturell):** der Kachel-Cache lebt jetzt dort, wo seine Lebensdauer tatsächlich zur Graph-Lebensdauer passt – auf `OsmnxDatastore.tile_cache` (osmnx_datastore.py), das nur bei Moduswechsel neu angelegt wird, genau wie `routing`/`rnodes`/`edge_shapes`. `MyRouter` referenziert jetzt `router.tile_cache` statt ein eigenes Dict zu bauen; das tote `RouteServer.stored_tiles` wurde entfernt. Derselbe fehlende Cache existierte im Streckenvorgabe-Pfad (`orienteering_router.plan_orienteering_route()`) ebenfalls – dort gab es bislang gar keinen Versuch, zu cachen –, jetzt ebenfalls über `datastore.tile_cache` behoben.
- **Verifiziert:** exakte Zwei-Such-Sequenz des Nutzers nachgestellt (gleiche Session/gleicher Router: erst Schleife mit 31 Kacheln, danach dieselben 31 Kacheln mit geändertem Ziel + einem Wegpunkt). Vorher wäre das die Konstellation, die den Fehler auslöst; nachher zeigt der zweite Suchlauf für **keine** der 31 Kacheln mehr "Tile X has N entry nodes" (vollständig aus dem Cache bedient, keine erneute Verarbeitung), `debug/luftlinie_debug.log` bleibt bei genau dem einen echten, unbedenklichen Eintrag (Straße ohne gespeicherte Kurvenform, aber korrekte Länge) – keine einzige neue falsche Luftlinie. Beide Suchen liefern erfolgreich eine Route (66,51 km bzw. 59,41 km).

---

## Bugfix: "wilde Sprünge" – zweite, tieferliegende Ursache gefunden und behoben (60-Kacheln-Fall)

- **Wieder aufgetreten, trotz vorherigem Fix:** Nutzer meldete den Sprung erneut bei einer ~60-Kacheln-Route (zweite reale GPX-Exportdatei). Die vorherige Diagnose-Log-Datei (`debug/luftlinie_debug.log`) feuerte tatsächlich – aber mit einem anderen Fehlerbild: diesmal war `edge_length()` nicht fehlend, sondern **falsch**: 10 Hops mit real 0,4–1,9 km Abstand waren mit einer `edge_length` von nur 14–25 m registriert. Die Diagnose-Instrumentierung selbst hat sich damit als korrekt erwiesen (sie hat den echten Fehler gefangen), aber die Ursache war eine andere als beim ersten Mal.
- **Reproduziert** mit den 59 realen Kacheln aus `debug/tiles.js` dieser Sitzung, direkt (ohne HTTP/Server) nachgestellt – derselbe Fehlausschlag reproduzierbar, inkl. exakt der geloggten Knotenpaare.
- **Ursache gefunden:** `Tile.get_entry_points()` (tile.py) wurde pro Kachel **zweimal** aufgerufen – einmal in `MyRouter._run()` (korrekt, mit Zwischenspeicherung in `self.stored_tiles`), und ein zweites Mal redundant in `ortools_router._tile_representative_node()`, das sich bisher ein eigenes, frisches `Tile`-Objekt für dieselbe Kachel-ID gebaut hat. `get_entry_points()` schützt nur die *gleiche Instanz* vor doppelter Ausführung (früher Return, wenn `self.entryNodeId` schon gesetzt ist) – nicht die Kachel als solche. Der zweite Aufruf durchsucht `router.routing` erneut, findet dabei aber ein bereits durch den ersten Aufruf verändertes Straßennetz (die künstlichen Eintrittsknoten des ersten Durchlaufs sind schon eingefügt) und entdeckt dadurch eine **andere Anzahl** an Kreuzungspunkten (beobachtet z. B. Kachel 8700_5660: 10 vs. 14 Eintrittsknoten; Kachel 8701_5660: 5 vs. 7). Da die künstliche Knoten-ID (`Kachel-UID + laufender Zähler innerhalb dieses einen Aufrufs`) beim zweiten Durchlauf wieder bei 0 beginnt, werden dieselben IDs für **andere, physisch entfernte** Kreuzungspunkte vergeben – und überschreiben dabei `edge_lengths`/`edge_shapes`-Einträge, die eigentlich zu einem ganz anderen Straßenabschnitt gehören. Ergebnis: ein echter ~1,6 km entfernter Punkt wird plötzlich mit ~21 m Kantenlänge registriert – die Luftlinie, die OR-Tools dann als scheinbar günstige "Abkürzung" wählt. Derselbe Doppel-Aufruf-Fehler steckte auch in `orienteering_router.solve_orienteering_route()`.
- **Fix (strukturell, nicht nur Patch):** `_tile_representative_node()` (ortools_router.py) nimmt jetzt ein bereits verarbeitetes `Tile`-Objekt entgegen, statt selbst `get_entry_points()` aufzurufen. `solve_tile_route()` und `solve_orienteering_route()` erhalten die bereits von `MyRouter._run()` bzw. `plan_orienteering_route()` verarbeiteten `Tile`-Objekte direkt, statt roher Kachel-IDs. Damit läuft `get_entry_points()` pro Kachel und Suche garantiert nur noch genau einmal.
- **Zusätzliches Sicherheitsnetz für Stabilität ("wie bekommen wir das stabiler?"):** `_cost_graph()` (ortools_router.py) prüft jetzt für jede Kante, ob die registrierte Länge plausibel ist – eine echte Straße kann nie kürzer sein als die Luftlinie zwischen ihren beiden Endpunkten (abzüglich kleiner Fließkomma-Toleranz). Unterschreitet eine Kante das (weniger als 90 % der Luftlinie), wird die Luftlinien-Distanz als Ersatzwert verwendet. Das fängt diese ganze Fehlerklasse strukturell ab – unabhängig davon, wodurch eine `edge_length` in Zukunft nochmal verfälscht werden könnte – statt nur den einen jetzt gefundenen Auslöser zu beheben.
- **Verifiziert:** derselbe 59-Kacheln-Fall (zuvor 10 falsche Diagnose-Log-Einträge) läuft jetzt mit leerem `debug/luftlinie_debug.log` durch (keine einzige verdächtige Luftlinie mehr), jede Kachel wird in den Server-Logs nur noch genau einmal mit ihrer Eintrittsknoten-Anzahl ausgegeben (vorher: doppelt, mit unterschiedlichen Zahlen), Route erfolgreich berechnet (119,94 km statt vorher 124,71 km mit den fehlerhaften Abkürzungen – die neue Zahl ist die tatsächlich richtige, da keine Fake-Shortcuts mehr die Distanzmatrix verzerren).

---

## Bugfix: "wilde Sprünge"/Luftlinien im OR-Tools-Pfad – Ursache gefunden und behoben

- **Diagnose eingebaut:** `Route._build_latlons()` (tilesrouter.py) loggt jetzt jeden Verbindungs-Hop >0,3 km, für den `shape_between()` keine Kurvenform liefert, mit Knoten-IDs, Koordinaten und `edge_length()`-Wert nach `debug/luftlinie_debug.log` – Grundlage für die eigentliche Ursachensuche unten.
- **Reale Reproduktion statt Vermutung:** anhand einer vom Nutzer bereitgestellten GPX-Datei (mit auffällig vielen 1–2,3 km "Sprüngen", mehrere davon exakt eine Kachelbreite) und des zugehörigen `debug/tiles.js`-Protokolls die betroffenen 25 Kacheln extrahiert und denselben Suchlauf direkt (ohne HTTP/Server) nachgestellt – reproduzierbarer Absturz "No path between 13064151170 and 870356593".
- **Ursache gefunden:** `OsmnxDatastore.find_node()` (Koordinate → nächstgelegener Straßenknoten, genutzt für Start/Ziel/Wegpunkte) prüfte nicht, ob der geometrisch nächste Knoten im aktuellen Fahrmodus überhaupt eine befahrbare Kante hat. Der gewählte Startpunkt lag am nächsten an einem Knoten, der ausschließlich über einen für "Roadcycle" ausgeschlossenen Wegtyp erreichbar ist (`self.routing[node] == {}`). `ortools_router.py`s Distanzmatrix behandelt so einen unerreichbaren Knoten nicht als *verboten*, sondern nur als "sehr teuer, aber endlich" (`UNREACHABLE_PENALTY_M`) – OR-Tools kann den Knoten trotzdem wählen, die anschließende Pfad-Rekonstruktion (`nx.shortest_path`) findet dafür aber keinen echten Weg (Absturz) bzw. bei einer kleinen, nicht komplett isolierten Straßeninsel eine unrealistische "Abkürzung" (die gerade Linie).
- **Fix 1** (`osmnx_datastore.py`, `find_node()`): sucht jetzt mit wachsendem Radius (0,15–5 km, gleiches Prinzip wie `allow_gravel_near()`) nach dem nächstgelegenen *tatsächlich befahrbaren* Knoten, statt blind den geometrisch nächsten zurückzugeben.
- **Fix 2** (`ortools_router.py`, `solve_tile_route()`): prüft vor dem Lösen, ob alle Kacheln/Wegpunkte in derselben zusammenhängenden Komponente wie der Startknoten liegen – falls nicht, sauberer Fehlschlag (`"no_route"`) statt eines Absturzes oder einer verzerrten, aber rechnerisch "günstigen" Sackgassen-Lösung.
- **Verifiziert:** derselbe 25-Kacheln-Fall, der vorher mit "No path between ..." abstürzte, berechnet jetzt erfolgreich eine 53,98-km-Route ohne jede Diagnose-Meldung (>0,3 km); `find_node()` liefert für dieselbe Startkoordinate jetzt einen verbundenen Knoten statt des vorher isolierten.

---

## Vier TODO-Punkte umgesetzt: Kartennavigation, Server-Threading, Übersetzungen, Solver-Anzeige

- **Karte: eigene Ortung + Sprung zum größten Quadrat.** Neue Kartensteuerung `#mapNavControl` (unter dem Leaflet-Zoom-Regler) mit zwei Buttons: GPS-Ortung (Browser-Geolocation-API, zentriert die Karte auf die aktuelle Position) und Sprung zum aktuell größten Quadrat (nutzt die Bounds des bereits geladenen `maxSquareLayer`, kein neuer Server-Endpunkt nötig). Verifiziert mit gemockter Geolocation-Position und echten gecachten Statshunters-Daten (Karte springt korrekt auf die reale Max-Square-Geometrie).
- **Server blockiert nicht mehr komplett bei hängendem Import:** `route-tiles-server.py` nutzt jetzt `socketserver.ThreadingTCPServer` statt `socketserver.TCPServer` (`daemon_threads = True`, damit der Prozess trotz eines noch laufenden hängenden Requests sauber beendet werden kann). Verifiziert: ein Request gegen eine nicht auflösbare Adresse hängt, ein zweiter, gleichzeitiger Request kommt trotzdem in ~13ms durch (vorher: komplette Blockade bis zu ~1 Stunde).
- **Übersetzungen vervollständigt (Englisch, Französisch, Deutsch):** neue `static/i18n/de.json` (bisher gab es nur en/fr), Sprachumschalter bietet jetzt auch Deutsch an. Alle im Zuge der GUI-Überarbeitung dieser Sitzung neu hinzugekommenen, bis dahin hart codierten Texte (Panel-Titel, Buttons, Kartenlegende, Kartennavigation-Tooltips, Schotter-Dialog, Rundtour-Hinweis) auf `data-i18n` umgestellt; alle dynamisch per JavaScript gesetzten Statusmeldungen (Statshunters-Ladezustand, Format-/Machbarkeits-Fehlermeldungen, Geolocation-Fehler, Zeitschätzung, "Abgebrochen", Max-Square-Vervollständigungstext) nutzen jetzt `$.i18n()` mit Parametersubstitution statt fest codiertem Text. Nebenbei zwei kleinere, bereits vorher bestehende Lücken im Original-Projekt mitgezogen ("Routes:"-Label, Umbenennen-Dialog nutzte `prompt("Nom", ...)` unabhängig von der gewählten Sprache). Verifiziert: alle drei Sprachen durchgeschaltet, Panel-Titel/Buttons/Segmented-Control/Kartennavigation/Legende sowie mehrere dynamische Meldungen zeigen in jeder Sprache den korrekten Text, keine JavaScript-Fehler.
- **Streckensuche-Art neben der Kachelanzahl:** "N Kacheln ausgewählt" zeigt jetzt zusätzlich, welcher Solver-Pfad für die aktuelle Anzahl (inkl. Wegpunkte) verwendet würde – "Präzisionsmodus" (exakter Algorithmus, ≤15) oder "Turbo-Modus" (OR-Tools, >15), ebenfalls vollständig übersetzt. Verifiziert: 1 Kachel → Präzisionsmodus, 16 Kacheln → Turbo-Modus, Schwelle exakt bei `OR_TOOLS_TILE_THRESHOLD` getroffen.

---

## GUI-Anordnung als abgeschlossen markiert

Nach mehreren Iterationen (Panels, Segmented Control, angeheftete/schwebende Aktionsleiste, Sichtbarkeits-Toggles auf die Karte, diverse Feinjustierungen) wird die aktuelle Anordnung als zufriedenstellend eingestuft. Weitere grundsätzliche Umbauten werden nicht mehr verfolgt, sofern nicht neues konkretes Feedback dazu aufkommt.

## Feature: Geschätzte Suchdauer während der Routenberechnung

- **Neues Modul `route_timing.py`:** `record_timing(solver, param_value, elapsed_s)` hängt nach jeder erfolgreich abgeschlossenen Suche einen Datenpunkt an eine persistente Historie an (`route_timing_history.json`, gitignored – reine Laufzeitdaten, kein Quellcode), begrenzt auf die letzten 500 Einträge. `estimate_time(solver, param_value)` schätzt die Dauer für eine neue Suche durch lineare Interpolation zwischen den beiden Historien-Punkten (gleicher Solver), die den angefragten Wert einschließen, bzw. lineare Extrapolation an den Rändern (unterhalb des kleinsten bekannten Werts: flache Fortschreibung, um keine unplausibel niedrigen/negativen Werte zu erzeugen).
- **Aufzeichnung** in `tilesrouter.py`: `MyRouter._run()` misst die Solver-Laufzeit (`time.monotonic()`) um den eigentlichen Lösungsaufruf (exakter Algorithmus oder OR-Tools, je nach `OR_TOOLS_TILE_THRESHOLD`) und speichert bei Erfolg `(solver, Anzahl_Kacheln, Sekunden)`. `OrienteeringRunner._run()` macht dasselbe für den Streckenvorgabe-Pfad mit `(orienteering, Budget_km, Sekunden)`. Bewusst nur bei echtem Erfolg aufgezeichnet – abgebrochene/fehlgeschlagene Suchen sagen nichts darüber aus, wie lange eine vollständige Lösung normalerweise dauert.
- **Neuer Endpunkt `/estimate_route_time`** (`route-tiles-server.py`) liefert die Schätzung für gegebenen Solver + Parameter.
- **Frontend:** Beim Klick auf "Route planen" wird parallel zum eigentlichen Suchstart eine Schätzung angefragt (Kachelanzahl bzw. Budget-km, Solver-Typ über denselben Schwellwert wie serverseitig bestimmt) und, sobald verfügbar, neben "Searching route..." eingeblendet (z. B. "Searching route... (ca. 12 s geschätzt)"). Ohne ausreichende Historie für den jeweiligen Solver erscheint kein Schätzwert, statt einer erfundenen Zahl.
- **Noch offen (siehe `TODO.md`):** eine repräsentative Sammlung von Testsuchen (verschiedene Kachelanzahlen/Budgets) im Vorfeld durchlaufen zu lassen, um die Historie gezielt zu befüllen, statt sie nur organisch durch echte Nutzung wachsen zu lassen.
- **Verifiziert:** `route_timing.py`s Interpolation/Extrapolation direkt getestet (exakte Treffer, Zwischenwerte, Werte unter-/oberhalb der bekannten Spanne – alle rechnerisch korrekt); `/estimate_route_time`-Endpunkt per curl gegen künstlich eingetragene Historie geprüft; Frontend-Anzeige mit abgefangener (gemockter) `/route_status`-Antwort verifiziert ("Searching route... (ca. 2 s geschätzt)" erscheint korrekt), keine JavaScript-Fehler.

---

## Dropdown-Ausrichtung, Streckenvorgabe-Machbarkeitsprüfung, Kacheln-Reset, echter Klick-durch-Bug behoben

- **Dropdown-Ausrichtung korrigiert:** "Aktivitätstyp", "Mode" und "Turnaround cost" reichten rechts weiter als das Statshunters-Link-Feld. Ursache: Bootstraps `.row` hat negative Außenränder (um die Innenabstände seiner `.col-*`-Kinder auszugleichen), ein einfaches `.form-control` daneben im selben `.card-body` hat das nicht – dadurch lagen die rechten Kanten nicht übereinander. Fix: `.card-body .form-group.row { margin-left: 0; margin-right: 0; }`. Betrifft auch den "+"-Button bei "Gespeicherte Routen" (lag vorher ebenfalls zu weit rechts).
- **Streckenvorgabe: manuell ausgewählte Kacheln werden jetzt zurückgesetzt**, sobald auf den Modus "Streckenvorgabe" umgeschaltet wird (`selected_tiles`/`gravel_tiles` leeren, Karte neu zeichnen) – vorher blieben sie fälschlich sichtbar, obwohl für diesen Modus irrelevant.
- **Streckenvorgabe + gesetzter Endpunkt: grobe Machbarkeitsprüfung ergänzt.** Vor dem Absenden der Suche wird jetzt die Luftlinien-Distanz Start↔Ende (`mymap.distance()`) gegen das gewählte Budget geprüft – reicht das Budget dafür schon rechnerisch nicht aus (echte Straßendistanz ist immer ≥ Luftlinie), erscheint sofort eine klare Fehlermeldung mit den konkreten Zahlen, statt eine zum Scheitern verurteilte Suche zu starten.
- **Echten Bug gefunden und behoben: Klick auf "Route planen"/"Abbrechen" wählte eine Kachel im Hintergrund an/ab.** Ursache: `#mapActionBar` & Co. liegen als normale Kind-Elemente *innerhalb* von `#mapid` (nicht außerhalb), ein Klick auf einen ihrer Buttons bubbelt im DOM trotz `pointer-events`-Absicherung weiterhin bis zu `#mapid` hoch – Leaflets eigener Karten-Klick-Handler (Kachel-Auswahl-Logik) feuerte dadurch zusätzlich für die Bildschirmposition des Buttons. Fix: `L.DomEvent.disableClickPropagation()` auf `#mapBottomOverlay` und `#mapVisibilityControl` (derselbe Mechanismus, den Leaflets eigene eingebaute Controls intern nutzen).
- **Verifiziert:** Playwright – alle vier Punkte gegen den echten Server getestet (Dropdown-Kanten deckungsgleich, Kacheln-Reset beim Moduswechsel, Warnmeldung bei 1 km Budget vs. 64,3 km Luftlinie, normales Verhalten bei ausreichendem Budget, kein Kachel-Toggle mehr nach Klick auf Route planen/Abbrechen), keine JavaScript-Fehler.

---

## Download-Button in "Gespeicherte Routen" verschoben, "Route planen" nicht mehr dauerhaft hervorgehoben

- **Download-Button geklärt:** der Icon-Button (Wolke-Symbol) unterhalb von "Route planen" in der schwebenden Kartenleiste war `#button-download-route` – lädt die gerade berechnete (noch nicht als Trace gespeicherte) Route direkt als GPX herunter (separat von `#togpx-trace` im "Gespeicherte Routen"-Dropdown, das eine bereits gespeicherte Route herunterlädt). Auf Wunsch aus `#mapActionBar` heraus- und in die Karte "Gespeicherte Routen" verschoben (eigene beschriftete Zeile "Berechnete Route herunterladen"), Sichtbarkeitslogik (`.show()`/`.hide()` je nach Routenstatus) unverändert, da rein ID-basiert.
- **"Route planen" nicht mehr optisch hervorgehoben:** war `btn-primary` (komplett gefüllt), dadurch wirkte der Button dauerhaft "aktiv"/ausgewählt statt schlicht als eine von drei gleichwertigen Aktionen. Jetzt `btn-outline-primary`, passend zu "Kacheln leeren" und "Abbrechen".
- **Verifiziert:** Playwright – Download-Button steckt jetzt in `#section-routes`, nicht mehr in `#mapActionBar`; `#bPlanRoute` hat die neue Outline-Klasse; keine JavaScript-Fehler.

---

## Start/End-Buttons zeigen jetzt farblich, ob sie gesetzt sind

- **Umgesetzt** (Variante 1 der drei vorgeschlagenen Mockups): `#bStart`/`#bEnd` sind jetzt `btn-outline-primary` im ungesetzten Zustand, füllen sich beim Setzen komplett mit der Farbe des zugehörigen Kartenpins (`--marker-start` Grün / `--marker-end` Orange, passend zu den bereits bestehenden `L.ExtraMarkers`-Pinfarben) und bekommen ein Häkchen-Suffix. Neue `updateMarkerButtonStates()` (`static/index.js`) hält das synchron mit `markers['start']`/`markers['end']`, aufgerufen aus `add_marker()`/`remove_marker()`.
- **Rundtour-Hinweis:** "End" zeigt im ungesetzten Zustand zusätzlich "(= Rundtour)" – macht das bereits bestehende Verhalten (kein Endpunkt → automatische Rundtour zum Start, siehe `start_route()`) sichtbar, statt es nur implizit zu lassen.
- **Verifiziert:** Playwright – Button-Klassen/Badge/Rundtour-Hinweis wechseln korrekt beim Setzen/Löschen; Drag-and-Drop zum Verschieben funktioniert weiterhin unverändert nebenher (Leaflets Draggable unterdrückt das synthetische Klick-Event nach einem echten Drag, dadurch löst ein Verschieben nicht versehentlich das neue Klick-zum-Löschen aus) – per Test bestätigt: Marker ziehen bewegt ihn (bleibt gesetzt), einfacher Klick ohne Bewegung löscht ihn.

---

## "Draw circle"-Feature entfernt, Start/End-Marker löschen sich jetzt wie Zwischenstationen

- **"Draw circle" komplett entfernt:** Checkbox+Radius-Feld aus dem Panel "Fortbewegung & Route" sowie die zugehörige `update_circle()`-Logik/`circle_layer` in `static/index.js` restlos herausgenommen (wurde nicht mehr benötigt).
- **Einheitliches Lösch-Verhalten für Start/End/Zwischenstationen:** bisher mussten Start/End über einen separaten Papierkorb-Button (`#bClearStart`/`#bClearEnd`) entfernt werden, bevor sie neu gesetzt werden konnten – Zwischenstationen ließen sich dagegen schon immer direkt per Klick auf den Kartenpin entfernen. Jetzt einheitlich: Klick auf den Start-/End-Pin entfernt ihn direkt (`add_marker()` bekommt denselben Klick-Handler wie `add_waypoint()`), die beiden separaten Löschen-Buttons sind komplett entfernt.
- **Verifiziert:** Playwright – Start-Marker setzen, per Klick auf den Pin wieder entfernen, keine JavaScript-Fehler.
- **Drei Gestaltungsvorschläge erstellt** (noch nicht umgesetzt, Entscheidung steht aus) für die Frage, wie Start/End-Buttons sichtbar machen sollen, dass sie schon gesetzt sind – inkl. Berücksichtigung, dass ein nicht gesetzter Endpunkt automatisch eine Rundtour zum Start ergibt (bereits bestehendes Verhalten in `start_route()`, hier nur in der Beschriftung sichtbar gemacht).

---

## Button-Umbenennung, Link-Format-Validierung, Sichtbarkeits-Toggles auf die Karte verlagert

- **Button-Beschriftung:** `msg-import-statshunters` (en/fr) von "Reload from statshunters"/"Recharger..." auf "Load from statshunters"/"Charger depuis statshunters" geändert.
- **Format-Hinweis + Validierung beim Statshunters-Link:** Eingabefeld hat jetzt einen Platzhalter mit Beispiel-Format (`https://statshunters.com/share/abcdef123456/` – bewusst eine erfundene Beispiel-ID, keine echte). Neue `isValidStatshuntersUrl()` (`static/index.js`) prüft das Format clientseitig (akzeptiert sowohl den nackten Sharelink als auch Varianten mit zusätzlichem Pfad wie `/activities`, siehe letzter Eintrag), bevor überhaupt ein Request rausgeht – klare Fehlermeldung über `#statshuntersStatus` statt eines verwirrenden Server-Fehlschlags.
- **Sichtbarkeits-Toggles von der Sidebar auf die Karte verlagert:** "Show visited tiles"/"Show max square"/"Show cluster" sind jetzt ein neues schwebendes Kartensteuerelement `#mapVisibilityControl` (oben rechts auf der Karte, analog zu `#mapActionBar`/`#mapLegend`) statt drei Checkboxen im Sidebar-Panel "Kartendaten" – gleiche IDs/Klassen (`config-storage`, `showVisitedTiles` etc.), daher keine JS-Änderung an der eigentlichen Logik nötig, nur Markup-Umzug + neues CSS.
- **Dabei zwei weitere Abstürze bei leeren Kachelmengen gefunden und behoben** (derselbe Bug-Typ wie beim vorherigen `compute_cluster()`/`compute_max_square()`-Eintrag, diesmal aber schon bei komplett leerer statt nur kleiner Kachelmenge, z. B. ein wohlgeformter aber nie importierter/leerer Sharelink):
  - `compute_max_square()`: `unary_union([])` auf eine leere Polygon-Liste erzeugt eine Geometrie, die `fastkml` nicht serialisieren kann (`ValueError: Illegal geometry type`) – jetzt früher Rückgabewert `0` bei leerer Kachelmenge (konsistent mit `compute_cluster()`s bestehendem Verhalten für den "kein Cluster"-Fall).
  - `compute_cluster()`: `list(tiles)[0]` auf eine leere Menge wirft `IndexError: list index out of range`, **noch vor** der eigenen bestehenden Leer-Prüfung weiter unten in derselben Funktion – jetzt ganz am Anfang der Funktion abgefangen.
- **Verifiziert:** Playwright gegen den echten Server – ungültiges Linkformat zeigt sofort die Fehlermeldung ohne Request; ein wohlgeformter, aber nie importierter Link (vorher: harter Serverabsturz, mehrdeutig als "Serverfehler 200" im Frontend sichtbar) liefert jetzt korrekt "0 Kacheln geladen"; ein echter gecachter Link lädt weiterhin normal; Sichtbarkeits-Toggles sitzen sichtbar auf der Karte, Sidebar-Panel "Kartendaten" enthält sie nicht mehr; keine JavaScript-Fehler.

---

## Bugfix: Statshunters-Sharelinks mit zusätzlichem Pfad (z. B. `/activities`) luden falsche/keine Daten

- **Gemeldet:** `https://statshunters.com/share/abcdef123456/activities` (Link inkl. Pfad-Anhängsel, wie er z. B. beim Kopieren aus der Statshunters-Aktivitätsansicht entstehen kann) lud nichts.
- **Ursache:** `statshunters.py`, `statshunters_path()` nahm bisher naiv das **letzte** URL-Pfadsegment als Cache-Ordner-Schlüssel (`sharelink_url.split('/')[-1]`) – bei diesem Link also `"activities"` statt der eigentlichen Share-ID `abcdef123456`. Dieselbe unveränderte URL wurde außerdem direkt für den echten API-Request weiterverwendet (`get_statshunters_activities()`), wodurch dort `.../share/abcdef123456/activities/api/activities?page=1` entstand – ein doppelt verschachtelter, ungültiger Pfad.
- **Fix:** neue `_normalize_share_url()` extrahiert per Regex zuverlässig `https://<host>/share/<id>` aus beliebigen Varianten (Pfad-Anhängsel, Trailing Slash, Query-Parameter) und wird jetzt sowohl in `statshunters_path()` als auch in `get_statshunters_activities()` angewendet, bevor die URL für Cache-Schlüssel bzw. API-Request verwendet wird.
- **Verifiziert:** `https://statshunters.com/share/abcdef123456/activities` liefert jetzt korrekt alle 2389 Kacheln aus dem bereits gecachten `abcdef123456`-Ordner (vorher: falscher/leerer Ordner `activities`), sowohl direkt gegen den Endpoint als auch im Browser über Playwright, keine JavaScript-Fehler.

## Sicherheitsfix + Redesign: Aktivitätsfilter, Import-Status, Tile-Potential

- **Sicherheitslücke gefunden und behoben:** `statshunters.py`, `tiles_from_activities()` hat den Inhalt des Freitext-Filterfelds bisher direkt per Python-`eval(filter_str, globals(), activity)` ausgewertet – jeder, der den Server erreichen konnte, hätte darüber beliebigen Python-Code zur Ausführung bringen können. Ersatzlos entfernt.
- **"Filter on activities" (Freitextfeld, für Nutzer ohne Doku unbenutzbar) ersetzt durch ein einzelnes festes Dropdown "Aktivitätstyp"** (Default "Alle Typen"), gleiche schlichte Bauart wie die übrigen Auswahlfelder in diesem Panel. `statshunters.py` bekommt dafür `activity_filter_options()` (liest die tatsächlich in den importierten Daten vorkommenden Typen aus) sowie eine neue, sichere `tiles_from_activities(activities_dir, activity_type=None)`-Signatur (einfacher Vergleich statt `eval`). Server-Endpunkte (`/statshunters`, `/statshunters_filter`, `/scoring`, `/start_orienteering`) nehmen jetzt `type` statt `filter` entgegen; `/statshunters`+`/statshunters_filter` liefern zusätzlich `filterOptions` mit, aus denen das Frontend das Dropdown nach jedem Import befüllt.
  - *Iteriert:* erste Version war eine Mehrfachauswahl-Liste (`<select multiple>`) plus separatem Jahres-Dropdown – auf Rückmeldung hin ("viel zu groß", Jahr nicht benötigt) auf ein einziges normales Einzel-Dropdown reduziert, Jahresfilter komplett entfernt (Frontend, Server-Endpunkte, `statshunters.py`).
- **Import-Statusanzeige:** neues `#statshuntersStatus`-Element zeigt jetzt durchgehend, was gerade passiert – "Lade Daten von Statshunters …" während der Anfrage, "N Kacheln geladen · zuletzt aktualisiert um HH:MM:SS" bei Erfolg, Fehlermeldung bei Anwendungsfehler oder Server-/Netzwerkfehler. Vorher gab es dafür überhaupt keine Rückmeldung im Erfolgsfall und nur ein `alert()` bei einer bestimmten Fehlerklasse – ein tatsächlicher Netzwerk-/Serverfehler (kein `error:`-Callback im `$.ajax`-Aufruf) blieb bisher komplett unbemerkt.
- **"Tile potential"-Dropdown entfernt:** die Option "Cluster growth" (`score_cluster_candidates()`, orange Einfärbung) ist komplett herausgenommen (Funktion + `BRIDGE_WEIGHT` aus `scoring.py` gelöscht, `clusterScores`/`clusterScoresMax` aus dem Frontend entfernt). Die Option "Max square growth" (`find_best_square_completion()`, lila Einfärbung der für das nächstgrößere Quadrat fehlenden Kacheln) bleibt vollständig erhalten, läuft jetzt aber **immer automatisch** statt über eine Auswahl – wird nach jedem Import/Filter-Wechsel neu berechnet und dauerhaft angezeigt. Kartenlegende um den dadurch überflüssig gewordenen "Cluster-Potenzial"-Eintrag bereinigt (der `#showCluster`-Toggle für den Cluster-**Umriss** ist davon nicht betroffen, das ist eine separate, unveränderte Funktion).
- **Nebenbei echten Bug gefunden und behoben:** Ein enger Aktivitätstyp-Filter (z. B. nur "GravelRide", 12 statt 2389 Kacheln) ließ die Kartenanzeige mit einem JS-Fehler abstürzen. Ursache: `compute_cluster()`/`compute_max_square()` (`statshunters.py`) geben den blanken Int `0` statt eines KML-Strings zurück, wenn es für die (jetzt realistisch kleine, gefilterte) Kachelmenge keine vollständig umgebene "Innenkachel" bzw. kein Quadrat gibt – `omnivore.kml.parse()` im Frontend hatte dafür keinerlei Abfangen. Fix: `static/index.js` prüft `data.cluster`/`data.maxSquare` jetzt auf Wahrheitswert, bevor es geparst wird. Der Bug war schon vorher latent vorhanden, kam aber erst durch einen tatsächlich benutzbaren Filter praktisch zum Tragen.
- **Verifiziert:** gegen echte gecachte Statshunters-Antworten (`data/abcdef123456`, 2389 Kacheln über mehrere Jahre/Aktivitätstypen) – Dropdown befüllt sich korrekt (17 Aktivitätstypen), Filterung reduziert die Kachelzahl korrekt (2389 → 271 für GravelRide korrekt runter auf 12 Kacheln ohne Absturz) und aktualisiert die Max-Square-Info live, keine JavaScript-Fehler.
- **Nebenbefund (nicht behoben, siehe `TODO.md`):** Der Server (`socketserver.TCPServer`, nicht threaded) blockiert komplett, wenn `get_statshunters_activities()` gegen eine nicht erreichbare Adresse läuft – die `@retry(...)`-Kette kann den einzigen Verarbeitungsthread für bis zu ~1 Stunde blockieren. Beim Testen selbst ausgelöst und den Testserver damit lahmgelegt.

## GUI-Überarbeitung: Gruppierte Panels, Segmented Control, angeheftete Aktionsleiste

- **Umsetzung** des zuvor abgestimmten Vorschlags (statisches Mockup, siehe vorheriger `TODO.md`-Eintrag) in `static/index.html`/`static/index.js`. Bewusst *kein* Wechsel des Frontend-Stacks (weiterhin Bootstrap 4/jQuery, siehe Modernisierungs-Audit in `TODO.md`) – nur Umstrukturierung/Restyling der bestehenden Bootstrap-Bausteine, damit alle JS-gesteuerten Widgets (Modal, Dropdown, Popover, Collapse) unverändert funktionieren.
- **Gruppierung:** die bisher flach aufgelisteten Bedienelemente sind jetzt fünf klar abgegrenzte, einzeln einklappbare Bootstrap-`.card`-Panels (Kartendaten / Fortbewegung & Route / Ziel: Kacheln wählen / Status / Gespeicherte Routen). "Gespeicherte Routen" ist standardmäßig eingeklappt (selten gebraucht), die anderen vier offen. Die Sprachauswahl sitzt als eigene Zeile oberhalb der Panels.
- **Segmented Control:** Manuell/Streckenvorgabe nutzt jetzt Bootstraps `btn-group-toggle` statt einzeln stehender Radio-Buttons – technisch weiterhin dieselben `<input type="radio" name="routingMode">`-Elemente, daher unverändertes JS (`$('input[name="routingMode"]:checked')`).
- **Angeheftete Aktionsleiste:** "Kacheln leeren"/"Route planen"/"Abbrechen" (`#run-button-group`) stehen jetzt in einer eigenen `#actionBar` mit `position: sticky; bottom: 0`, bleiben also beim Scrollen der rechten Spalte immer sichtbar, statt mitten im Formular zu stehen.
- **Kleine Ergänzung:** Im Manuell-Modus zeigt `#selectedTileCount` jetzt die Anzahl aktuell ausgewählter Kacheln an (aktualisiert bei Kachel-Klick, "Kacheln leeren", Schotter-Dialog "Kachel entfernen" und beim Laden aus `localStorage`).
- **Verifiziert:** lokaler Server + Playwright (headless Chromium) – alle fünf Panels rendern und lassen sich unabhängig ein-/ausklappen, Segmented Control schaltet `#manualModeControls`/`#budgetModeControls` korrekt um, Aktionsleiste bleibt beim Scrollen sichtbar, keine JavaScript-Fehler in der Konsole.

### Nachtrag: optisch entsprach die erste Umsetzung nicht dem Mockup

- **Rückmeldung:** die erste Umsetzung übernahm nur die *Struktur* des Mockups (Panels/Segmented Control/Sticky Bar), nicht dessen *Optik* – Farben/Formen/Typografie blieben unverändertes Bootstrap-Blau/-Grau.
- **Nachgezogen:** Farbsystem als CSS-Variablen (`--bg`, `--surface`, `--ink`, `--accent` (Petrol/Teal `#1F6F72`) etc., 1:1 aus dem Mockup übernommen) über gezielte Bootstrap-Overrides gelegt – `.btn-primary`/`.btn-outline-primary` (inkl. dessen aktivem Zustand, trifft damit auch den Segmented Control), Fokus-Ringe, Checkbox/Switch-Akzentfarbe, `.card`/`.card-header` (abgerundete Ecken, Schatten, keine graue Kopfleiste mehr), Eingabefelder. Panel-Titel und Buttons nutzen jetzt die im Mockup verwendete Schriftart "Archivo Narrow" (Google Fonts, per `<link>` nachgeladen). Die Aktionsleisten-Buttons entsprechen jetzt dem Mockup: "Kacheln leeren" outline, "Route planen" gefüllt in Akzentfarbe, "Abbrechen" outline-danger (vorher warning/success/danger-Vollflächen).
- **Verifiziert:** erneuter Playwright-Screenshot gegen den echten Server zeigt die Akzentfarbe korrekt auf Buttons/Segmented Control/Cards angewendet, keine JavaScript-Fehler.

### Nachtrag: Aktionsleiste, Status und Fortschrittsbalken in "Ziel: Kacheln wählen" zusammengeführt

- **Anforderung:** "Kacheln leeren"/"Route planen"/"Abbrechen" sowie das komplette Status-Panel (Fortschritt, Länge, GPX-Download) sollen nicht mehr eigenständig (Sticky-Bar bzw. eigenes "Status"-Panel) stehen, sondern Teil des Panels "Ziel: Kacheln wählen" sein – dort, wo Kacheln/Budget gewählt werden, direkt weiter zu Planen/Status.
- **Umsetzung:** die Sticky-Action-Bar (`#actionBar`) und das eigenständige `#card-status`-Panel entfallen; `#run-button-group`, `#progress-message`, `#gpxMessage` und `#gpxDownload` sind jetzt Teil von `#card-target`.
- **Neu (bisher ungenutzter Server-Wert):** ein echter Fortschrittsbalken (Bootstrap `.progress`/`.progress-bar`, `#routeProgressBar`) – der Server liefert in `/route_status` seit Längerem ein `progress`-Feld (0–100, siehe `route-tiles-server.py`/`tilesrouter.py`), das das Frontend bisher komplett ignorierte und nur den Spinner+Text anzeigte. `index.js` aktualisiert die Balkenbreite jetzt bei jedem Poll und setzt sie beim Start einer neuen Suche sowie bei Abbruch/Fehler auf 0 zurück.
- **Verifiziert:** Playwright gegen den echten Server – alle Elemente liegen im DOM an der neuen Stelle (`#card-status`/`#actionBar` existieren nicht mehr), keine JavaScript-Fehler; Fortschrittsbalken testweise auf 45% gesetzt und Darstellung geprüft.

## Fix: Browser-Cache konnte alte index.html/index.js ausliefern

- **Symptom:** Nutzer meldete, dass bereits behobene Bugs (automatischer Routenstart im manuellen Modus, fehlende Buttons im Streckenvorgabe-Modus) weiterhin auftraten. Serverseitiger Abgleich (`curl` gegen `/index.html`/`/index.js`) zeigte, dass der Server exakt den aktuellen, korrekten Stand ausliefert (byte-identisch zur Datei auf der Festplatte) – der Fehler lag also nicht mehr im Code, sondern vermutlich an einer vom Browser gecachten alten Version dieser beiden Dateien (werden ohne Cache-Busting-Dateinamen/-Query ausgeliefert).
- **Fix:** `route-tiles-server.py`, `RouteHttpServer.end_headers()` überschrieben, setzt jetzt `Cache-Control: no-store` auf jede Antwort (sowohl statische Dateien als auch JSON-Endpoints). Verhindert, dass dieser Verwirrungs-Typ ("mein Fix kommt nicht an") während der aktiven Weiterentwicklung erneut auftritt.
- **Nutzer-Handlungsempfehlung bei diesem Symptom:** einmalig Hard-Refresh (z. B. Cmd+Shift+R) nötig, danach liefert der Header dauerhaft frischen Stand.

## UX-Überarbeitung: Einheitlicher Ablauf für beide Modi + Abbrechen-Button

- **Anforderung:** Beide Modi (manuelle Kachelauswahl und Streckenvorgabe) sollen sich identisch verhalten – nichts passiert automatisch beim Klicken/Umschalten, es gibt in beiden Modi denselben "Route planen"-Button, dazu einen "Abbrechen"-Button. "Clear tiles" bleibt in beiden Modi sichtbar.
- **Umsetzung:**
  - `request_route()` (bisher: plante nach 2s automatisch eine Berechnung, ausgelöst durch Kachel-Klicks, Marker-Verschieben, Waypoints etc.) ist jetzt ein No-op. Zustandsänderungen passieren weiterhin sofort, es wird aber nichts mehr an den Server geschickt.
  - Ein gemeinsamer Button **"Route planen"** (`#bPlanRoute`) prüft beim Klick den aktuellen Modus und ruft je nachdem `/start_route` (manuell) oder `/start_orienteering` (Streckenvorgabe) auf.
  - Neuer Button **"Abbrechen"** (`#bAbortRoute`) + neuer Server-Endpoint `/abort_route` (nutzt die bereits vorhandene `RouteServer.abort()`/`MyRouter.abort()`/`OrienteeringRunner.abort()`-Kette). Bekannte Einschränkung: greift erst am nächsten Kontrollpunkt, kann einen bereits laufenden, blockierenden OR-Tools-Solve-Aufruf nicht mitten drin unterbrechen.
  - "Route planen" wird während der Suche deaktiviert, "Abbrechen" aktiviert – und umgekehrt bei Abschluss/Fehler/Abbruch.
- **Verifiziert:** manueller Modus weiterhin unverändert erfolgreich (13,43 km, identisch zu vorherigen Tests), `/abort_route`-Endpoint antwortet korrekt.

### Nachtrag: echter Bug beim Testen des Abbrechen-Buttons gefunden und behoben

Beim gezielten Testen gegen eine länger laufende Berechnung (20 Kacheln → löst über den OR-Tools-Pfad, `MyRouter._run()` in `tilesrouter.py`) zeigte sich: der Abbruch wurde vom Server zwar entgegengenommen (`/abort_route` antwortete mit `status: OK`), hatte aber **keinerlei Wirkung** – die Route wurde trotzdem vollständig zu Ende berechnet und als Erfolg zurückgegeben. Ursache: nach dem blockierenden `solve_tile_route()`-Aufruf gab es (anders als im exakten Algorithmus und im Orienteering-Pfad) keine Prüfung von `self._exit` mehr, bevor die Route als abgeschlossen markiert wurde.

**Fix** (`tilesrouter.py`, `MyRouter._run()`, direkt nach dem `solve_tile_route()`/`do_route_with_crossing_zone()`-Aufruf): zusätzliche `if self._exit: self.error_code = ERR_ABORT_REQUEST; return False`-Prüfung, bevor die Route weiterverarbeitet wird.

**Verifiziert:** 20-Kacheln-Testfall (OR-Tools-Pfad, `time_limit_s`≈20s) – vor dem Fix lieferte `/route_status` nach Abbruch trotzdem die fertige 36,3-km-Route; nach dem Fix liefert derselbe Testfall korrekt `{"status": "Fail", "error_code": 2, ...}` (bereits vorhandene i18n-Meldung "Abort request"/"Demande d'arrêt").

Weiterhin unverändert gültig: der Abbruch kann den einzelnen blockierenden OR-Tools-Solve-Aufruf selbst nicht mitten drin unterbrechen, sondern greift erst, sobald dieser Aufruf zurückkehrt (bei den hier verwendeten Zeitlimits typischerweise nach wenigen bis ~20 Sekunden).

## Bugfix: Streckenvorgabe startete manchmal ohne Klick auf "Route planen"

- **Ursache:** Ein aus dem manuellen Modus noch ausstehender, 2 Sekunden verzögerter `request_route()`-Aufruf (z. B. durch kurz zuvor angeklickte Kacheln) konnte nach dem Umschalten auf "Streckenvorgabe" trotzdem feuern – die Modus-Prüfung saß nur in `request_route()` selbst, nicht in der tatsächlich ausführenden `start_route()`.
- **Fix:** `start_route()` prüft den Modus jetzt selbst zusätzlich (zweite Absicherung), und beim Umschalten in den Streckenvorgabe-Modus wird ein noch ausstehender Timeout sofort verworfen.

## Feature: Streckenvorgabe ab Start – GUI/Server-Anbindung

- **Server:** `tilesrouter.py`, neue Klasse `OrienteeringRunner` – dupliziert absichtlich `MyRouter`s Schnittstelle (`progress`/`is_complete`/`error_code`/`min_route`/`abort`), läuft im selben `RouteServer.myRouter`-Slot, dadurch funktioniert das bestehende `/route_status`-Polling **unverändert** auch für diesen neuen Modus. Neuer Endpoint `/start_orienteering` (Start, Budget-km, Modus, Statshunters-URL/Filter).
- **GUI:** Neuer Umschalter "Manuelle Kachelauswahl" / "Streckenvorgabe" (Radio-Buttons). Im Streckenvorgabe-Modus erscheint ein Eingabefeld (Ziel-km) + Button "Route planen" anstelle der Kachel-Aktionen; die automatische Requestauslösung durch Kachel-Klicks bleibt im Streckenvorgabe-Modus stumm (kein versehentliches Auslösen des alten Fix-Kachel-Flows).
- Vom Solver gewählte Kacheln werden nach Abschluss automatisch wie manuell ausgewählte Kacheln hervorgehoben (`selectedTiles`-Feld in der `/route_status`-Antwort, nur vorhanden wenn der aktuelle Runner ein `OrienteeringRunner` ist).
- **Verifiziert über den echten Server:** identisches Ergebnis wie beim Backend-Test (9 Kacheln, 18/20 km), manueller Modus weiterhin unverändert funktionsfähig (Regressionstest).

## Feature (Backend): Streckenvorgabe ab Start – Kernalgorithmus

- **Ziel:** Ab Startpunkt + Ziel-Streckenlänge (Budget in km) die beste Route mit möglichst viel **zusammenhängender** neuer Kachel-Abdeckung finden – ein Orienteering-Problem (maximiere gesammelten Wert innerhalb eines Distanz-Budgets), im Unterschied zu den bisherigen Solvern, die eine feste Kachelmenge erzwingen und Distanz minimieren.
- **Neues Modul `orienteering_router.py`:**
  - `_generate_candidates()`: alle noch nicht besuchten Kacheln im plausiblen Reichweiten-Radius (0,35× Budget, konservativ statt großzügig – siehe Bugfix unten), statische Prämie = 1 + 2 × Anzahl bereits besuchter Nachbarn (belohnt Anschluss an die bestehende Fläche). Kandidaten werden auf ~150 gedeckelt, sortiert nach Prämie/Entfernungs-Dichte.
  - `solve_orienteering_route()`: Google OR-Tools mit einer Distanz-**Dimension** (harte Obergrenze = Budget) und jeder Kandidatenkachel als **optionalem** Knoten (`AddDisjunction`) mit Straf-Gewicht = Prämie fürs Auslassen.
- **Bug unterwegs gefunden und behoben:** Erster Versuch kollektierte nur 6 Kacheln bei 48% Budgetnutzung (9,7 von 20 km) – die Zielfunktion minimiert (gefahrene Distanz + Strafe für ausgelassene Kacheln), das ist **nicht dasselbe** wie "maximiere Kacheln innerhalb des Budgets": bei zu kleiner Prämien-Skalierung lohnt sich ein Umweg für eine niedrig bewertete Kachel rechnerisch oft nicht, obwohl noch Budget übrig ist. Fix: Prämien-Skalierung deutlich erhöht (1000 → 8000), sodass das Einhalten des Budgets (harte Grenze) wichtiger wird als die Fahrstrecke selbst zu minimieren.
  - Ergebnis nach Fix: **9 Kacheln statt 6, 90% Budgetnutzung statt 48%** (18 von 20 km) – verifiziert **alle 9 Kacheln bilden eine einzige zusammenhängende Gruppe**.
  - Nebenbei auch die Kandidatenauswahl verbessert: ursprünglich rein nach Prämie sortiert, dadurch waren bis zu 26 km entfernte (bei 20 km Budget unerreichbare) Kacheln unter den Top-150 und verdrängten näher gelegene, tatsächlich erreichbare Kandidaten. Jetzt nach Prämie/Entfernungs-Dichte sortiert.
- **Noch offen:** Server-Endpoint und GUI-Anbindung (Budget-Eingabefeld, Button) – bisher nur eigenständig gegen echte Statshunters-Daten getestet, noch nicht über den Server erreichbar.

## Bugfix: Schotter-Freigabe schaltete ganzes Nebennetz statt Stichweg frei

- **Problem (siehe `TODO.md`-Befund):** Selbst der kleinste ausreichende Freigabe-Radius schaltete hunderte Kanten frei, die dann als generelles Abkürzungsnetz für unabhängige Streckenabschnitte genutzt wurden – Dutzende unrealistische Sprünge in der Route.
- **Fix:** `osmnx_datastore.py`, `allow_gravel_near()` komplett umgebaut: sucht jetzt nur noch temporär (committet nichts) alle Schotter-Kandidatenkanten im Radius, findet darin den **kürzesten Pfad** von der Kachel zum nächsten bereits ans reguläre Netz angebundenen Knoten, und schreibt **nur diesen einen Pfad** dauerhaft in `self.routing`. Der Radius bestimmt nur noch, wie weit gesucht werden darf – nicht mehr, wie viel dauerhaft freigeschaltet wird.
- **Verifiziert:**
  - Anzahl committeter Kanten pro Kachel: 7, 3, 6 (statt 578, 227, ... zuvor)
  - Alle drei bekannten Problem-Kacheln finden weiterhin einen Eingangspunkt
  - **0 Sprünge >0,5km** im kompletten 130-Kacheln-Härtetest (vorher: Dutzende)
  - Bekannter Einzelkachel-Testfall über den echten Server-Pfad weiterhin erfolgreich

## Modernisierung: `mercantile` statt eigener Tile-Mathematik

- **Was:** `tile.py`s handgeschriebene Web-Mercator-Formeln (`tile_from_coord`, `coord_from_tile`, `geom_from_tile`) durch die Standardbibliothek `mercantile` ersetzt (war eine der ursprünglichen Empfehlungen vom Sitzungsbeginn, bis jetzt nicht umgesetzt).
- **Verifiziert vor der Umstellung:** alte vs. neue Formel über 2000+ Zufallskoordinaten plus Testfälle verglichen – **0 Abweichungen** bei `coord_from_tile` (6084 getestete Kacheln), nur 2 Abweichungen bei `tile_from_coord`, beide bei 89,9°/-89,9° Breite (nahe den Polen, wo die alte Formel unkontrolliert überläuft, `mercantile` aber sauber auf den gültigen Bereich begrenzt – für jede reale Tile-Hunting-Koordinate identisch, `mercantile` sogar robuster).
- **Regressionstests nach der Umstellung:** Tile-Konstruktion (Rundreise Koordinate→Kachel→Koordinate), Statshunters-Import (2389 Tiles), `find_best_square_completion` (identisches Ergebnis: Größe 24, 5 Kacheln), reale Routenberechnung über den Server (identische Länge/Punktzahl wie vorher) – alle unverändert.
- Nur `tile.py` geändert (Funktionssignaturen exakt beibehalten), keine Anpassung an Aufrufstellen (`route_cleanup.py` u. a.) nötig.

## Bugfix: Luftlinien an Kachel-Eingangspunkten (häufigste Ursache)

- **Problem:** Bei jeder besuchten Kachel wird die kreuzende Straße an der Kachelgrenze aufgeschnitten und ein synthetischer Eingangsknoten eingefügt (`tile.get_entry_points()`). Dabei gingen die gespeicherte Kurvenform und echte Länge der ursprünglichen Kante für die beiden neuen Teilstücke komplett verloren – da das bei **jeder** Kachel mindestens zweimal passiert (rein, raus), war das die mit Abstand häufigste Ursache für Luftlinien-Abschnitte in der Route (50 betroffene Stellen in einer 35-Kacheln-Testroute, verglichen mit 2 beim vorherigen Einbahnstraßen-Fix).
- **Fix:** `tile.py`, `get_entry_points()` teilt jetzt die ursprüngliche Kurve proportional auf die neuen Teilstücke auf (basierend darauf, wo der Eingangspunkt entlang der Originalkante liegt) und überträgt Kurvenpunkte sowie Länge korrekt auf `router.edge_shapes`/`router.edge_lengths`.
- **Verifiziert:** Alle 50 zuvor fehlenden Stellen lösen jetzt korrekt auf (0 verbleibend). Anzahl der Routenpunkte stieg dadurch von selbst (1593 → 1893 in der Testroute) – nicht durch künstliches Hinzufügen von Punkten, sondern weil jetzt echte Kurvendaten statt Geradenersatz verwendet werden. Routenlänge stieg leicht (z. B. 12,85 km → 13,43 km bei der kleinen Testroute), was korrekt ist: die Luftlinien-Abkürzungen hatten die echte (kurvige) Distanz bisher unterschätzt.

## Feature: Sackgassen-Bereinigung (redundante Umwege entfernen)

- **Problem:** Die Routing-Solver wählen pro Kachel einen einzelnen Eingangspunkt und fahren gezielt dorthin – wenn die Route dieselbe Kachel später ohnehin nochmal durchquert, war der frühere Extra-Abstecher (rein, gleicher Weg raus) reine Verschwendung.
- **Lösung:** Neues Modul `route_cleanup.py`, `remove_redundant_spurs()`: durchsucht die fertige Routen-Knotenfolge nach Schleifen (Route kehrt zu einem bereits besuchten Knoten zurück). Für jede Schleife wird geprüft, ob alle darin abgedeckten Zielkacheln **auch außerhalb** der Schleife abgedeckt werden – wenn ja, wird die komplette Schleife herausgeschnitten. Start/Ende/Waypoints sind explizit geschützt (werden nie versehentlich mit entfernt), ebenso wird die allerletzte Knotenposition nie als Schleifenende behandelt (sonst würde eine Rundtour komplett auf den Startpunkt kollabieren).
- **Eingebunden** in `tilesrouter.py`, direkt nach erfolgreicher Routenberechnung (für beide Solver-Pfade), vor der finalen `Route`-Konstruktion.
- **Verifiziert:** 4 synthetische Testfälle (redundante Sackgasse, notwendige Sackgasse, Rundtour-Erhalt, reiner Leerlauf) korrekt behandelt. Reale 35-Kacheln-Testroute schrumpfte von 65,8 km auf **55,4 km (-15%)** bei weiterhin vollständiger Abdeckung aller 35 Kacheln; kleine 8-Kacheln-Testroute (exakter Algorithmus) blieb unverändert (hatte von vornherein keine Sackgassen).

## Bugfix: Luftlinien-Abschnitte trotz Kurven-Fix (Einbahnstraßen rückwärts)

- **Problem:** Trotz des früheren Kurven-Fixes traten weiterhin einzelne Luftlinien-Abschnitte auf, besonders in großen (OR-Tools-)Routen. Ursache: der Kostengraph des OR-Tools-Solvers ist bewusst **ungerichtet** (Fix gegen Einbahnstraßen-Fallen), kann eine echte Einbahnstraße also auch **rückwärts** durchqueren. `edge_shapes`/`edge_lengths` waren aber nur für die ursprüngliche Richtung `(u, v)` gespeichert – rückwärts gab es keinen Treffer, die Route sprang per Luftlinie.
- **Fix:** `osmnx_datastore.py`, `shape_between()` und `edge_length()` prüfen jetzt **beide Richtungen** (`(u,v)` und `(v,u)`), Kurvenpunkte werden bei Rückwärtsnutzung entsprechend umgekehrt zurückgegeben.
- **Verifiziert:** Konkret gefundene kaputte Segmente in einer 35-Kacheln-Testroute lösen jetzt korrekt auf (Kurvenpunkte + echte Länge statt Luftlinie).

## Feature: Gravelbike-Modus

- Neues Fahrmodus-Profil `gravelbike` in `pyroutelib3.py` (TYPES): anders als Roadcycle sind unbefestigte Tracks/Pfade **erwünscht** (Gewicht 1,0 für Tracks), nicht ausgeschlossen. Netzwerk-Zuordnung (`bike`) in `osmnx_datastore.py`, neuer Eintrag im Modus-Dropdown der GUI.

## UX-Fix: Schotter-Dialog

- **Problem:** Verschachtelte `confirm()`-Dialoge ("Abbrechen" bedeutete "zeig mir weitere Optionen") waren unintuitiv.
- **Fix:** Echtes Bootstrap-Modal (`#gravelModal`) mit drei eindeutig beschrifteten Buttons: "Schotter zulassen" / "Kachel entfernen" / "Abbrechen".

## Feature: Karten-Legende

- Neues fest positioniertes Panel (`#mapLegend`, unten rechts auf der Karte) erklärt alle verwendeten Farben (besucht/nicht besucht/Cluster-Potenzial/Max-Square-Ziel/Schotter akzeptiert/Routenlinie/Cluster-Umriss/Max-Square-Umriss).

## Feature: Schotter-Freigabe pro Kachel (Gravel-Fallback)

- **Problem:** Manche Kacheln haben im gewählten Modus (z. B. Roadcycle) keine befahrbare Straße (nur Feld-/Waldwege), Routenberechnung schlägt fehl.
- **Lösung:**
  - `osmnx_datastore.py`: `OsmnxDatastore.allow_gravel_near(lat, lon, radius_km=1.5)` – schaltet lokal bereits heruntergeladene, aber bisher ausgeschlossene Wege (Feldwege, Trampelpfade) frei, indem die permissivere "trail"-Gewichtstabelle für Kanten in der Nähe angewendet wird. Kein Zweit-Download nötig.
  - `tilesrouter.py`: `MyRouter` bekommt `gravel_tiles`-Parameter; vor der Eingangspunkt-Suche wird für Kacheln in dieser Menge automatisch `allow_gravel_near()` aufgerufen.
  - `route-tiles-server.py`: neuer Query-Parameter `gravelTiles[]`.
  - Frontend: Bei Fehler "kein Eingangspunkt" (error_code 1) erscheinen zwei verschachtelte Dialoge für drei Ergebnisse: Schotter akzeptieren / Kachel entfernen / Abbrechen.
  - Kacheln mit akzeptiertem Schotter werden dauerhaft **braun** (`saddlebrown`) hervorgehoben, unabhängig vom aktiven Overlay-Modus.
- **Aufgeräumt:** Der stille Fallback in `ortools_router.py` (bei fehlendem Eingangspunkt einfach nächsten – ggf. unerreichbaren – Knoten nehmen) wurde entfernt. Er war nur ein Notbehelf vor dieser Lösung; die gemeinsame Vorbereitungsschleife in `MyRouter._run()` garantiert jetzt für beide Routing-Pfade einen echten Eingangspunkt, bevor überhaupt geroutet wird.

## Feature: OR-Tools-Solver für große Kachelmengen (bis ~100)

- **Problem:** Der ursprüngliche Suchalgorithmus (`do_route_with_crossing_zone`) verfolgt den Zustand *(Knoten, Menge noch nicht besuchter Kacheln)* – bei N Kacheln bis zu 2^N Zustände. Ab ca. 15-20 Kacheln praktisch nicht mehr berechenbar.
- **Lösung:** Neues Modul `ortools_router.py`:
  - Jede Kachel wird auf einen repräsentativen, garantiert erreichbaren Punkt reduziert (wiederverwendet die bestehende `Tile.get_entry_points()`-Logik).
  - Distanzmatrix zwischen allen Wegpunkten via Multi-Source-Dijkstra auf einem eigenen, ungerichteten Kostengraphen (Distanz/Präferenz-Gewicht).
  - Google OR-Tools (Guided Local Search) löst die Rundreise mit festem Zeitlimit (15-90s, skaliert mit Kachelzahl) statt unbegrenzter Suche.
  - Route wird durch Aneinanderreihen echter Kürzester-Wege-Segmente zwischen den gewählten Wegpunkten rekonstruiert.
  - **Schwelle:** `OR_TOOLS_TILE_THRESHOLD = 15` in `tilesrouter.py` – darunter weiterhin der exakte Algorithmus (präziser, alle Eingangspunkte berücksichtigt), darüber automatisch OR-Tools.
- **Kompromiss:** Ein Punkt pro Kachel statt aller Eingangspunkte; ungerichteter Graph auf dieser groben Ebene (Einbahnstraßen zwischen weit entfernten Kacheln werden ignoriert, die feine Streckenwahl bleibt aber korrekt).
- **Unterwegs behobene Bugs:**
  - Isolierte Kachel-Repräsentativpunkte (keine gültige Kante) crashten den Distanzmatrix-Aufbau → alle bekannten Knoten werden jetzt explizit vorab in den Kostengraphen aufgenommen.
  - Einbahnstraßen-Fallen (erreichbar hin, nicht zurück) führten zu Widersprüchen zwischen Distanzmatrix und Pfad-Rekonstruktion → Kostengraph ist jetzt ungerichtet.
- **Verifiziert:** 35 Kacheln über den echten Server-Pfad in ~30s gelöst (vorher: exponentiell/unbrauchbar lange).

## Bugfix: Fehlender `turnaroundCost`-Parameter crasht Request

- `route-tiles-server.py`: `do_GET_start_route` crashte mit `KeyError: 'turnaroundCost'`, wenn das Frontend den Parameter nicht mitschickte (GUI-Zustand des Dropdowns). Jetzt mit Default `'0'` abgesichert.

## Bugfix: `maxspeed` als Liste crasht Gewichtsberechnung

- `pyroutelib3.py`: `weight_primary_roadcycle()` nahm an, `maxspeed` sei immer ein einzelner String. `osmnx` liefert bei zusammengefassten Straßenabschnitten mit unterschiedlichen Tempolimits eine Liste → `TypeError`. Jetzt robust gegen Listen und nicht-numerische Werte (Fallback auf 80).

## Bugfix: Luftlinien-Abschnitte in berechneter Route

- **Problem:** `osmnx`'s Graph-Vereinfachung (`simplify=True`) fasst Kettenstücke ohne Kreuzungen zu einer Kante zusammen, behält die echte Kurvenform aber nur als Zusatzattribut (`geometry`). Die Routen-Rekonstruktion nutzte bisher nur die zwei Endknoten jeder Kante → echte Luftlinien durch Kurven, nicht nur optisch, sondern auch in der Kostenberechnung.
- **Fix 1 (Anzeige/Länge):** `osmnx_datastore.py` speichert jetzt `edge_shapes` (echte Zwischenpunkte) pro Kante; `tilesrouter.Route._build_latlons()` fügt sie beim Rekonstruieren der Route ein.
- **Fix 2 (Routenwahl):** `osmnx_datastore.py` speichert zusätzlich `edge_lengths` (von `osmnx` präzise vorberechnete Kurvenlänge); `tilesrouter.segment_distance()` nutzt diese statt der Luftlinien-Distanz zwischen den Endknoten für die Kostenberechnung.
- **Verifiziert:** Bekannte Testroute wuchs von 105 auf 375 Routenpunkte (12,75 km → 12,88 km, dann mit korrigierter Kostenberechnung 12,85 km).

## Migration: Routing-Engine von `pyroutelib3` auf `osmnx`

- **Grund:** `pyroutelib3` lädt OSM-Daten live von der OSM-**Editier**-API (`api.openstreetmap.org/api/0.6/map`), die ein hartes Limit von 50.000 Knoten pro Anfrage hat – bei dichten Stadtgebieten (München-Zentrum) reproduzierbar überschritten, führte zu stundenlangen Retry-Loops. Kein Preprocessing, kein Caching der Graphstruktur, veraltetes Projekt.
- **Lösung:** Neues Modul `osmnx_datastore.py` mit Klasse `OsmnxDatastore`, die das komplette von `tilesrouter.py`/`tile.py` genutzte Interface der alten `pyroutelib3.Datastore` nachbildet (`rnodes`, `routing`, `get_area`, `find_node`, …), sodass der eigentliche Tile-Routing-Suchalgorithmus unverändert bleiben konnte.
  - Region wird einmal im Voraus heruntergeladen (`preload_region()`) und als Graph gecacht (`~/.osmnx_cache`), in einem 0,2°-Raster-Cache, statt bei jeder Kachel live nachzuladen.
  - Nearest-Node-Suche über räumlichen Index (scikit-learn BallTree) statt linearer O(n)-Schleife.
  - Gewichtungstabellen pro Fahrmodus 1:1 aus `pyroutelib3.TYPES` übernommen.
- **Bewusste Vereinfachung:** Abbiegeverbote (`forbiddenMoves`/`mandatoryMoves`) werden nicht mehr ausgewertet – `osmnx` liefert keine OSM-Turn-Restriction-Relationen, und die alte Implementierung war ohnehin nur eine grobe Näherung.
- **Unterwegs behobene Bugs (alle durch die neuen `shapely`/Bibliotheksversionen aufgedeckt):**
  - `tile.py`: `'MultiPoint' object is not iterable` – Shapely 2.0 erlaubt kein direktes Iterieren über Multi-Geometrien mehr → `.geoms` verwenden.
  - `tile.py`: `geom_type == "Line"` war ein Tippfehler (Shapely liefert nie `"Line"`, immer `"LineString"`) – dieser Zweig war seit jeher toter Code und ist erst durch obigen Fix zum ersten Mal überhaupt gelaufen.
  - `tile.py`: In besagtem `LineString`-Zweig wurden rohe Koordinaten-Tupel statt `Point`-Objekten erzeugt → `'tuple' object has no attribute 'x'`. Jetzt korrekt in `Point(...)` gewrappt.
  - `tilesrouter.py`: `MyRouter.run()` fängt jetzt jede unerwartete Exception im Hintergrund-Thread ab und setzt einen klaren Fehlerstatus (neuer Error-Code 1001), statt dass die GUI für immer bei "searching" hängen bleibt, ohne dass der Nutzer etwas davon erfährt.
  - `route-tiles-server.py`: `socketserver.TCPServer.allow_reuse_address = True`, damit der Server bei Neustarts nicht sporadisch mit "Address already in use" hängen bleibt.
- **Ergebnis:** Bekannte Testroute (14 Tiles) lief vorher mehrere Minuten oder hing komplett; danach 3-70 Sekunden je nach Kachelzahl.

## Feature: Kachel-Priorisierung (welche fehlende Kachel bringt den größten Nutzen?)

- Neues Modul `scoring.py`:
  - `score_cluster_candidates()`: Union-Find über besuchte Kacheln; Score = "Brücken-Bonus" (Zugewinn durch Verbinden zweier *getrennter* Cluster, dominiert den Score) + "Kompaktheits-Wert" (1-4, wie viele Nachbarn schon besucht sind – Lücken/Dellen füllen ist günstiger als den Rand einfach nach außen zu schieben).
    - *Erste Version* bewertete nur "resultierende Cluster-Größe" – degenerierte dazu, praktisch den kompletten Rand uniform einzufärben (jede Randkachel wächst den Cluster ja nur um +1). Bridge-Bonus-Aufteilung behebt das.
  - `find_best_square_completion()`: findet über alle Zonen und Quadratgrößen hinweg das Fenster mit der **geringsten Anzahl fehlender, zusammenhängender** Kacheln, um das aktuelle globale Max-Quadrat zu vergrößern (via Integral-Image/Prefix-Sum, O(1) Rechteck-Summen).
    - *Erste Version* verglich jede Zone gegen ihren eigenen lokalen Rekord statt gegen den globalen → winzige, irrelevante Zonen (z. B. eine einzelne Auslandsaktivität) erschienen fälschlich als "Verbesserung" ("Kacheln in der Pampa"). Fix: Baseline ist jetzt immer der globale Max-Square-Wert.
    - *Zweite Verfeinerung:* Kandidaten-Kacheln müssen jetzt eine **zusammenhängende** Gruppe bilden (4-Nachbarschaft geprüft), nicht nur eine beliebige Mindestanzahl – eine Tour deckt ohnehin 50-100 Kacheln ab, eine verstreute Handvoll Einzelkacheln ist kein sinnvolles Ziel.
- Neuer Server-Endpoint `/scoring`, neues Dropdown "Tile potential" in der GUI (None / Max square growth / Cluster growth).
- Frontend: fehlende Kacheln mit Potenzial werden orange eingefärbt (Cluster-Modus, logarithmisch skaliert) bzw. lila (Max-Square-Modus, die konkrete Zielgruppe der fehlenden Kacheln).

## Bugfix: KML-Namespace-Präfix verhindert Max-Square/Cluster-Anzeige

- **Problem:** Nach dem `fastkml`-Downgrade (s.u.) gibt `to_string()` alle Elemente mit `kml:`-Präfix aus (`<kml:Placemark>`). Der Frontend-Parser (`omnivore.kml.parse`) sucht aber nach unpräfixierten Tags (`<Placemark>`) und fand nie etwas – die Checkboxen "Show Max Square"/"Show Cluster" schienen wirkungslos, weil sie nur eine leere Ebene ein-/ausblendeten.
- **Fix:** `statshunters.py`, `getKmlFromGeom()` entfernt das `kml:`-Präfix aus dem generierten String.

## Bugfix: Besuchte-Kacheln-Einfärbung verschwindet beim Verschieben

- **Problem 1 (Zoom-Flackern):** Zwei-Finger-Trackpad-Pans lösen auf dem Mac oft `wheel`-Events aus, die Leaflet standardmäßig als Zoom interpretiert. Kombiniert mit `zoomSnap: 0.5` reichte ein kleiner Wackler, um unter die Zoom-10-Schwelle zu rutschen, bei der `updateMapTiles()` **alles** löschte.
  - *Zwischenfix:* Hysterese-Zone (erst unter Zoom 9 löschen). Reichte nicht bei größeren Zoom-Sprüngen.
  - *Endgültiger Fix:* Beim Herauszoomen werden keine neuen Kacheln mehr gezeichnet, aber bestehende **nie mehr gelöscht** – kein Grund mehr, das überhaupt zu tun.
- **Problem 2 (eigentliche Ursache):** `updateMapTiles()` ruft für bereits gezeichnete Kacheln bei jedem Re-Render `tile.select(0/1)` auf, was intern `Tile.update()` aufruft. Diese Funktion berechnete die Opacity **immer neu ab 0** (nur Selektion/Fehler/Highlight addiert) und überschrieb dabei die ursprünglich gesetzte Opacity (0,25 für besuchte Kacheln) unwiderruflich – trat schon beim ersten Verschieben auf, nicht graduell.
  - *Fix:* Basis-Opacity wird jetzt separat in `this.baseOpacity` gespeichert (übersteht `setStyle()`-Aufrufe), `update()` rechnet ab jetzt korrekt darauf auf.

## Feature: "Show visited tiles"-Toggle

- Neue Checkbox in der GUI, um die grüne Einfärbung besuchter Kacheln unabhängig von den anderen Overlays ein-/auszublenden.

## Bugfix: Mapbox-Hintergrundkarte tot

- Fest im Code hinterlegter Mapbox-Access-Token in `static/index.js` war gesperrt (403 Forbidden) – vermutlich wegen öffentlicher Sichtbarkeit im GitHub-Repo missbraucht. Ersetzt durch den kostenlosen Standard-OSM-Tile-Server (`tile.openstreetmap.org`), kein Token nötig.

## Bugfix: `fastkml` 1.4.0 inkompatibel

- Die installierte aktuelle `fastkml`-Version hat die komplette API umgebaut (`Placemark.geometry` ist jetzt read-only statt eines normalen Attributs) → Absturz beim Erzeugen von Max-Square/Cluster-KML. Fix: `fastkml<1.0` in `requirements.txt` gepinnt (letzte "klassische" API-Version).

## Bugfix: `numpy` 2.x entfernt `numpy.math`

- `utils.py` nutzte `from numpy import math` (alter, längst entfernter Alias). Ersetzt durch das eingebaute `import math`.

## Ausgangspunkt: Projekt-Setup

- Repository [route-tiles](https://github.com/BenoitBouillard/route-tiles) geklont nach `route_tiles/route-tiles` (Fund einer Recherche: das Tool deckt bereits Statshunters-Import, Cluster/Max-Square-Anzeige und Straßennetz-Routing zu ausgewählten Kacheln ab).
- Python-venv erstellt, Abhängigkeiten installiert.
- Verifiziert: Datenimport von Statshunters funktioniert technisch weiterhin (API-Struktur unverändert), 2387 Tiles erfolgreich aus echtem Share-Link geladen.
