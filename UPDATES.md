# Updates

Laufendes Änderungsprotokoll für dieses Projekt (Fork von [route-tiles](https://github.com/BenoitBouillard/route-tiles)). Neue Einträge werden **oben** ergänzt. Für die Begründung *warum* etwas so gebaut ist, siehe `DOCUMENTATION.md`.

---

## GUI-Überarbeitung: Gruppierte Panels, Segmented Control, angeheftete Aktionsleiste

- **Umsetzung** des zuvor abgestimmten Vorschlags (statisches Mockup, siehe vorheriger `TODO.md`-Eintrag) in `static/index.html`/`static/index.js`. Bewusst *kein* Wechsel des Frontend-Stacks (weiterhin Bootstrap 4/jQuery, siehe Modernisierungs-Audit in `TODO.md`) – nur Umstrukturierung/Restyling der bestehenden Bootstrap-Bausteine, damit alle JS-gesteuerten Widgets (Modal, Dropdown, Popover, Collapse) unverändert funktionieren.
- **Gruppierung:** die bisher flach aufgelisteten Bedienelemente sind jetzt fünf klar abgegrenzte, einzeln einklappbare Bootstrap-`.card`-Panels (Kartendaten / Fortbewegung & Route / Ziel: Kacheln wählen / Status / Gespeicherte Routen). "Gespeicherte Routen" ist standardmäßig eingeklappt (selten gebraucht), die anderen vier offen. Die Sprachauswahl sitzt als eigene Zeile oberhalb der Panels.
- **Segmented Control:** Manuell/Streckenvorgabe nutzt jetzt Bootstraps `btn-group-toggle` statt einzeln stehender Radio-Buttons – technisch weiterhin dieselben `<input type="radio" name="routingMode">`-Elemente, daher unverändertes JS (`$('input[name="routingMode"]:checked')`).
- **Angeheftete Aktionsleiste:** "Kacheln leeren"/"Route planen"/"Abbrechen" (`#run-button-group`) stehen jetzt in einer eigenen `#actionBar` mit `position: sticky; bottom: 0`, bleiben also beim Scrollen der rechten Spalte immer sichtbar, statt mitten im Formular zu stehen.
- **Kleine Ergänzung:** Im Manuell-Modus zeigt `#selectedTileCount` jetzt die Anzahl aktuell ausgewählter Kacheln an (aktualisiert bei Kachel-Klick, "Kacheln leeren", Schotter-Dialog "Kachel entfernen" und beim Laden aus `localStorage`).
- **Verifiziert:** lokaler Server + Playwright (headless Chromium) – alle fünf Panels rendern und lassen sich unabhängig ein-/ausklappen, Segmented Control schaltet `#manualModeControls`/`#budgetModeControls` korrekt um, Aktionsleiste bleibt beim Scrollen sichtbar, keine JavaScript-Fehler in der Konsole.

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
