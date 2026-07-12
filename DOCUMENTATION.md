# Dokumentation

Erklärt, **was** der Code macht und **warum** er es so macht. Für die Chronologie der Änderungen siehe `UPDATES.md`. Dieses Dokument wird laufend an den aktuellen Stand angepasst.

## Zweck des Projekts

Tile-Hunting-Hobby-Tool: die Welt ist in Kacheln unterteilt (Zoom-14-Tiles, ~1km², wie bei Squadrats/Statshunters/VeloViewer). Ziel ist es, möglichst viele zusammenhängende Kacheln bzw. ein möglichst großes Quadrat an besuchten Kacheln zu sammeln. Dieses Tool hilft dabei, Routen zu planen, die gezielt fehlende, wertvolle Kacheln abdecken.

Basis ist ein Fork von [route-tiles](https://github.com/BenoitBouillard/route-tiles) (Python-Server + Leaflet-Frontend), der bereits Statshunters-Import, Cluster/Max-Square-Berechnung und Straßennetz-Routing zu ausgewählten Kacheln mitbrachte. Die Routing-Engine wurde komplett ausgetauscht (siehe unten), und zwei neue Fähigkeiten (Kachel-Priorisierung, Routing für sehr große Kachelmengen) wurden ergänzt.

## Architektur-Überblick

```
Browser (Leaflet-Karte, static/index.html + index.js)
        │  HTTP GET (JSON)
        ▼
route-tiles-server.py  (Python http.server, ein Endpoint pro Aktion via /do_GET_<name>)
        │
        ├── statshunters.py     Import von Statshunters-Aktivitäten, Cluster-/Max-Square-KML
        ├── scoring.py          Welche fehlende Kachel bringt den größten Nutzen?
        ├── tilesrouter.py      Orchestriert die Routenberechnung (Tile-Suchalgorithmus)
        │       │
        │       ├── osmnx_datastore.py   Straßennetz-Datenquelle (ersetzt pyroutelib3)
        │       ├── ortools_router.py    Solver für sehr große Kachelmengen (>15)
        │       └── route_cleanup.py     Entfernt redundante Sackgassen aus der fertigen Route
        ├── orienteering_router.py  Streckenvorgabe ab Start (Budget statt fixer Kachelmenge, noch ohne Server-Endpoint)
        ├── tile.py             Kachel-Geometrie, Eingangspunkt-Erkennung
        └── pyroutelib3.py      Nur noch die Gewichtstabellen pro Fahrmodus (TYPES)
```

## Frontend (`static/index.html`, `static/index.js`)

Leaflet-Karte mit mehreren Overlays, die sich gegenseitig nicht stören sollen:

- **Kachel-Raster** (`updateMapTiles()`): zeichnet nur Kacheln im aktuell sichtbaren Kartenausschnitt und nur ab Zoom-Level 10 (Performance). Einmal gezeichnete Kacheln werden beim Herauszoomen nie mehr gelöscht, nur keine neuen mehr hinzugefügt – vermeidet Flackern bei Trackpad-Pans.
- **Farblogik pro Kachel** (Prioritätsreihenfolge, letzte gewinnt):
  1. Standard: unsichtbar (blau, Opacity 0)
  2. Besucht → grün (abschaltbar über "Show visited tiles")
  3. Nicht besucht, "Max square growth" aktiv und Teil der besten Vervollständigungs-Kachelgruppe → lila
  4. Nicht besucht, "Cluster growth" aktiv und Score > 0 → orange (Intensität = log-skalierter Score)
  5. Nicht besucht, sonst → rot umrandet
  6. **Schotter für diese Kachel akzeptiert → braun** (überschreibt alles andere, damit immer sichtbar bleibt, wo Schotter droht)
- **Tile-Objekt** (`L.Rectangle`-Erweiterung): `select()`/`error()`/`highlight()` setzen jeweils ein Flag und rufen `update()`, das die Opacity aus der bei Erzeugung gespeicherten `baseOpacity` plus Zuschlägen berechnet – nie einfach von 0 neu, sonst geht die Grundfarbe bei jedem Re-Render verloren (siehe `UPDATES.md`).
- **Routing-Formular**: Modus, Turnaround-Cost (Malus gegen Kehrtwenden, s.u.), Start/Ende/Waypoints, ausgewählte Kacheln (`selected_tiles`), Schotter-Freigaben (`gravel_tiles`).
- **Fehlerbehandlung "kein Eingangspunkt"**: zwei verschachtelte `confirm()`-Dialoge bilden drei Ergebnisse ab (Schotter akzeptieren / Kachel entfernen / abbrechen) – siehe `route_status`-Handler.
- **Modus-Umschalter (manuelle Kachelauswahl / Streckenvorgabe)**: bewusst kein automatisches Auslösen einer Berechnung – weder beim Umschalten des Modus noch beim Setzen von Kacheln/Markern/Waypoints (`request_route()` ist ein No-op). Einziger Auslöser ist der Klick auf **"Route planen"** (`#bPlanRoute`), der je nach gewähltem Modus intern `/start_route` (manuell) oder `/start_orienteering` (Streckenvorgabe) aufruft. Dazu ein gemeinsamer **"Abbrechen"**-Button (`#bAbortRoute`, ruft `/abort_route`), in beiden Modi identisch. "Clear tiles" ist unabhängig vom Modus immer sichtbar; nur das Eingabefeld für die Ziel-Streckenlänge (`#budgetModeControls`) wird je nach Modus ein-/ausgeblendet. `set_planning_buttons(searching)` steuert den disabled-Zustand von "Route planen"/"Abbrechen" während einer laufenden Berechnung.

## `route-tiles-server.py`

Einfacher `http.server`-basierter Server. Routing der Endpoints: `GET /<name>?...` → `self.do_GET_<name>()` (via `getattr`). Sessions werden über einen `sessionId`-Query-Parameter (nicht Cookies) verwaltet, in `sessionDict` gehalten, jede Session hat ihren eigenen `RouteServer`.

Wichtige Endpoints:
- `/statshunters`, `/statshunters_filter` – Aktivitäten laden/filtern, Cluster-/Max-Square-KML berechnen
- `/scoring` – Kachel-Priorisierungs-Scores (siehe `scoring.py`)
- `/start_route`, `/start_orienteering`, `/route_status` – Routenberechnung starten (manuell bzw. Streckenvorgabe) und abfragen (asynchron, im Hintergrund-Thread)
- `/abort_route` – setzt das Abort-Flag der laufenden `RouteServer`/`MyRouter`/`OrienteeringRunner`-Kette. Bekannte Grenze: greift erst am nächsten Kontrollpunkt zwischen Verarbeitungsschritten – ein bereits laufender, blockierender OR-Tools-`SolveWithParameters()`-Aufruf kann dadurch nicht mitten drin unterbrochen werden, sondern erst wenn dieser Aufruf selbst zurückkehrt. Wichtig: `MyRouter._run()` prüft `self._exit` explizit direkt nach diesem Aufruf (vor dem OR-Tools-Zweig fehlte diese Prüfung ursprünglich – ohne sie wurde eine abgebrochene Berechnung trotzdem als abgeschlossene Route zurückgegeben, siehe `UPDATES.md`).
- `/generate_gpx`, `/generate_kml_tiles` – Export

`RouteHttpServer.end_headers()` setzt auf jede Antwort `Cache-Control: no-store` (statische Dateien wie JSON-Endpoints) – ohne das konnte der Browser eine veraltete `index.html`/`index.js` zwischenspeichern und bereits behobene Bugs erneut "auftreten" lassen, obwohl der Server längst den aktuellen Stand auslieferte (siehe `UPDATES.md`).

`socketserver.TCPServer.allow_reuse_address = True` ist gesetzt, damit Server-Neustarts während der Entwicklung nicht sporadisch an "Address already in use" scheitern.

## `tilesrouter.py` – Routenberechnungs-Orchestrierung

### `MyRouter._run()` – Ablauf pro Anfrage

1. Für jede ausgewählte Kachel: `Tile`-Objekt erzeugen, ggf. `allow_gravel_near()` aufrufen (wenn Nutzer Schotter akzeptiert hat), dann `tile.get_entry_points(router)` – bricht mit `ERR_NO_TILE_ENTRY_POINT` ab, falls keine gefunden werden. **Diese Prüfung läuft für beide Routing-Pfade identisch, bevor überhaupt entschieden wird, welcher Solver läuft.**
2. Ab **mehr als 15 Kacheln** (`OR_TOOLS_TILE_THRESHOLD`): OR-Tools-Solver (`ortools_router.solve_tile_route`). Sonst: der ursprüngliche exakte Suchalgorithmus (`do_route_with_crossing_zone`).
3. Ergebnis wird in eine `Route` gewrappt (echte Kurvenpunkte statt Luftlinie zwischen Kreuzungen, s. u.).

### `do_route_with_crossing_zone()` – der exakte Original-Algorithmus

Best-First-Suche (A*-artig) über den Zustand *(aktueller Straßenknoten, Menge noch nicht besuchter Kacheln)*. Heuristik (`_min_dist`) schätzt die Restkosten durch rekursive Nearest-Neighbor-Abschätzung über die verbleibenden Kachel-Eingangspunkte. Exakt und berücksichtigt **alle** Eingangspunkte jeder Kachel – aber die Zustandsmenge hat bis zu 2^N Teilmengen bei N Kacheln, daher nur für ca. N < 15-20 praktikabel.

`explore_routes_tile_exit()` wird nur bei aktivem Turnaround-Cost gebraucht: berechnet mögliche Wege *durch* eine Kachel hindurch (Eintritt → Austritt), um zu prüfen, ob ein Austritt eine Kehrtwende erzwingen würde.

**Turnaround Cost:** Kein hartes Verbot, sondern ein Kostenaufschlag (in km) für jede unmittelbare Kehrtwende (A→B→A) – verhindert, dass der Algorithmus eine Sackgasse anfährt nur um eine Kachelecke zu berühren und exakt zurückzufahren. Bekannte Einschränkung (aus der Original-README übernommen): mit aktivem Turnaround-Cost findet der Algorithmus nicht zuverlässig die global optimale Route, es ist eine Heuristik.

### `Route` – Rekonstruktion der finalen Koordinatenliste

`osmnx`'s Graph-Vereinfachung fasst Kreuzungsfreie Kettenstücke zu einer Kante zusammen, behält die echte Kurvenform aber nur als Attribut. `_build_latlons()` fügt diese gespeicherten Zwischenpunkte (`router.shape_between(u, v)`) zwischen den Knoten ein – sonst würde die Route Kurven schnurgerade abschneiden, sowohl optisch als auch in der berechneten Länge.

### `segment_distance()` – Kantenkosten

Nutzt die von `osmnx` präzise vorberechnete **echte Kurvenlänge** einer Kante (`router.edge_length(u, v)`), nicht die Luftlinien-Distanz zwischen den beiden Endknoten – sonst würden stark kurvige Straßen in der Kostenrechnung unterschätzt. Fällt auf Luftlinie zurück, wenn wirklich keine Kanteninfo vorhanden ist (z. B. Start-/Endpunkt-Knoten, die nicht Teil des osmnx-Graphen sind).

**Kachel-Eingangspunkte sind hiervon nicht mehr betroffen:** `tile.get_entry_points()` (in `tile.py`) schneidet die kreuzende Straße an der Kachelgrenze auf und fügt einen synthetischen Knoten ein – das passiert bei jeder besuchten Kachel mehrfach. Ursprünglich gingen dabei Kurvenform und Länge der Originalkante komplett verloren (häufigste Quelle für Luftlinien-Abschnitte in der Route). Seit dem Fix teilt `get_entry_points()` die Originalkurve proportional auf die neuen Teilstücke auf (basierend auf der Position des Eingangspunkts entlang der Originalkante) und schreibt sie zurück in `router.edge_shapes`/`router.edge_lengths`.

### Tile-Koordinaten-Mathematik (`tile_from_coord`, `coord_from_tile`, `geom_from_tile`)

Nutzt die Standardbibliothek `mercantile` für die Umrechnung GPS ↔ Kachel-Koordinate (Standard-Web-Mercator-Kachelschema, Zoom-Level 14 - dasselbe Raster wie Squadrats/Statshunters/VeloViewer). Vor der Migration war das eine handgeschriebene Formel; verifiziert identisch für alle realen Koordinaten (0 Abweichungen über 6000+ Testkacheln, minimale Abweichung nur in Polnähe, wo `mercantile` sogar korrekter auf den gültigen Wertebereich begrenzt). Funktionssignaturen unverändert, keine Anpassung an Aufrufstellen nötig.

## `osmnx_datastore.py` – Straßennetz-Datenquelle

Ersetzt `pyroutelib3.Datastore` komplett, bildet aber deren **komplettes Interface** nach (`rnodes`, `routing`, `get_area`, `find_node`, `not_update_routing`, `forbiddenMoves`/`mandatoryMoves`), damit der bestehende Tile-Suchalgorithmus in `tilesrouter.py`/`tile.py` unverändert bleiben konnte – nur die Datenquelle wurde ausgetauscht.

**Warum die Migration?** `pyroutelib3` lud Straßendaten live von der OSM-**Editier**-API (gedacht für Kartografen, nicht für Routing) – hartes Limit von 50.000 Knoten pro Anfrage, in dichten Stadtgebieten reproduzierbar überschritten. Kein Caching der Graphstruktur, kein Preprocessing.

- **Region-Caching:** `preload_region()` lädt einmal im Voraus die Bounding Box aus Start/Ziel/allen Kacheln (+ Marge), gecacht in einem 0,2°-Raster auf Platte (`~/.osmnx_cache/*.graphml`). Folgeanfragen im selben Gebiet sind reine Cache-Treffer.
- **Gewichte pro Fahrmodus:** direkt aus `pyroutelib3.TYPES` übernommen (roadcycle/foot/trail/…), angewendet auf den `highway`-Tag jeder Kante beim Zusammenführen in `self.routing`.
- **`edge_shapes` / `edge_lengths`:** siehe oben (`Route`/`segment_distance`). `shape_between()`/`edge_length()` prüfen **beide Richtungen** `(u,v)` und `(v,u)` – der OR-Tools-Solver läuft auf einem ungerichteten Kostengraphen und kann eine echte Einbahnstraße rückwärts durchqueren; ohne den symmetrischen Lookup ginge für diesen einen Schritt die Kurvenform/Länge verloren und die Route würde dort per Luftlinie springen.
- **`allow_gravel_near(lat, lon, radius_km=1.5)`:** Schotter-Freigabe – gezielter Stichweg, kein Blanket-Unlock. Sammelt zunächst nur *Kandidaten*-Kanten in der Nähe, die im aktuellen Modus ausgeschlossen sind (Gewicht 0), mit der permissiveren "trail"-Gewichtstabelle. Aus diesen Kandidaten wird ein temporärer lokaler Graph gebaut, darin der **kürzeste Pfad** von der Kachel zum nächsten bereits regulär angebundenen Knoten (`self.routing`-Eintrag mit Gewicht > 0) gesucht, und **nur dieser eine Pfad** dauerhaft in `self.routing` übernommen. `radius_km` bestimmt nur den Suchradius, nicht mehr die Menge des dauerhaft Freigeschalteten.
  - *Warum nicht einfach alles im Radius freischalten (frühere Version):* Selbst der kleinste ausreichende Radius schaltete in gut vernetzten Gegenden hunderte Kanten frei – ein ganzes Nebennetz, das der Tour-Solver dann als generelle Abkürzung für unabhängige Streckenabschnitte nutzte (verifiziert: dieselbe große Route hatte ohne Schotter-Kacheln nur 1 Sprung >0,5km, mit der alten Freigabe Dutzende). Mit dem gezielten Stichweg: 0 solcher Sprünge.
  - Kein Zweit-Download nötig – die Wege sind meist schon im `bike`/`walk`-Netz enthalten, nur gewichtsmäßig ausgeschlossen.
- **Bewusste Vereinfachung:** Abbiegeverbote (`forbiddenMoves`/`mandatoryMoves`) bleiben leer. `osmnx` liefert keine OSM-Turn-Restriction-Relationen; die alte Implementierung war ohnehin nur eine grobe Näherung.

## `ortools_router.py` – Solver für sehr große Kachelmengen

Ab `OR_TOOLS_TILE_THRESHOLD` (15) Kacheln wird nicht mehr exakt gesucht, sondern:

1. Jede Kachel → **ein** repräsentativer, garantiert erreichbarer Punkt (via `Tile.get_entry_points()`, nicht per naiver Nearest-Node-Suche – die könnte auf einem für den Modus nicht erreichbaren Knoten landen).
2. Distanzmatrix zwischen allen so gewählten Wegpunkten (Start, Ende, Waypoints, Kachel-Repräsentanten) via Multi-Source-Dijkstra auf einem **ungerichteten** Kostengraphen (Kosten = echte Distanz / Modus-Präferenz-Gewicht).
   - *Ungerichtet bewusst:* ein gerichteter Graph kann einen Repräsentativpunkt in einer Einbahnstraßen-Tasche isolieren (hin erreichbar, zurück nicht), was zu Widersprüchen zwischen Matrix und Pfad-Rekonstruktion führt. Auf dieser groben "in welcher Reihenfolge besuche ich die Kacheln"-Ebene ein akzeptabler Kompromiss.
3. Google OR-Tools (`RoutingModel`, Guided Local Search, Zeitlimit 15-90s je nach Kachelzahl) löst die Rundreise mit festem Start-/Endknoten.
4. Rekonstruktion der finalen Knotenfolge durch Aneinanderreihen echter Kürzester-Wege-Segmente zwischen den vom Solver gewählten Wegpunkten.

**Kompromiss gegenüber dem exakten Algorithmus:** nur ein Eingangspunkt pro Kachel statt aller – Preis für die Skalierbarkeit auf ~100 Kacheln in vorhersagbarer Zeit.

## `orienteering_router.py` – Streckenvorgabe ab Start

Beantwortet eine andere Frage als `ortools_router.py`: nicht "besuche diese festen Kacheln möglichst kurz", sondern **"ab hier, mit X km Budget, welche Kacheln lohnen sich am meisten?"** – ein klassisches Orienteering-Problem (maximiere gesammelten Wert innerhalb eines Distanz-Budgets).

**Läuft immer über OR-Tools, unabhängig von der Kachelzahl:** anders als der manuelle Modus (`MyRouter._run()`), der erst ab `OR_TOOLS_TILE_THRESHOLD` (15 Kacheln) von `do_route_with_crossing_zone()` auf OR-Tools umschaltet, kennt dieser Pfad den Schwellwert gar nicht – `solve_orienteering_route()` wird immer aufgerufen, auch wenn am Ende nur wenige Kacheln herauskommen. Sinnvoll, weil vor der Suche gar nicht feststeht, wie viele es werden (bei 30 km Budget realistisch deutlich mehr als 15), der alte exakte Algorithmus dafür also ohnehin nicht in Frage käme.

1. **`_generate_candidates()`:** alle noch nicht besuchten Kacheln in einem konservativen Radius (0,35× Budget – eine Rundtour muss hin *und* zurück, echte Straßendistanz ist immer länger als Luftlinie). Statische Prämie: `1 + 2 × Anzahl bereits besuchter Nachbarn` (belohnt Anschluss an die bestehende Fläche, ohne die volle Bridge-Bonus-Formel aus `scoring.py` zu benötigen). Auf ~150 Kandidaten gedeckelt, sortiert nach **Prämie/Entfernung** (Dichte), nicht nach roher Prämie – sonst verdrängen weit entfernte, ohnehin unerreichbare Kacheln näher gelegene, tatsächlich einsammelbare.
2. **`solve_orienteering_route()`:** OR-Tools mit einer Distanz-**Dimension** (harte Obergrenze = Budget, `AddDimension`) und jeder Kandidatenkachel als **optionalem** Knoten (`AddDisjunction`) mit Straf-Gewicht = Prämie fürs Auslassen. Nutzt denselben Kostengraphen/dieselbe Distanzmatrix-Logik wie `ortools_router.py` (`_cost_graph`, `_tile_representative_node`, wiederverwendet statt dupliziert).

**Wichtige Erkenntnis beim Bauen:** OR-Tools minimiert standardmäßig *(gefahrene Distanz + Strafe für ausgelassene Knoten)* – das ist **nicht** dasselbe wie "maximiere Kacheln innerhalb des Budgets". Bei zu niedriger Prämien-Skalierung (`PRIZE_SCALE`) lohnt sich ein Umweg für eine niedrig bewertete Kachel rechnerisch oft nicht, obwohl noch Budget übrig wäre – der Solver bricht dann zu früh ab (verifiziert: 48% statt 90% Budgetnutzung bei zu kleiner Skalierung). Fix: `PRIZE_SCALE` deutlich hochgesetzt (8000), sodass das Ausschöpfen des Budgets (harte Grenze) gegenüber reiner Distanzminimierung überwiegt.

**Server/GUI:** `tilesrouter.OrienteeringRunner` dupliziert bewusst `MyRouter`s Schnittstelle (`progress`/`is_complete`/`error_code`/`min_route`/`abort`) und läuft im selben `RouteServer.myRouter`-Slot – das bestehende `/route_status`-Polling brauchte dadurch keine Änderung. Neuer Endpoint `/start_orienteering` (Start, Budget-km, Modus, Statshunters-URL/Filter). GUI-Umschalter "Manuelle Kachelauswahl" / "Streckenvorgabe": im zweiten Modus ersetzt ein Budget-Eingabefeld + "Route planen"-Button die Kachel-Aktionen, die automatische Requestauslösung durch Kachel-Klicks bleibt dort stumm. Vom Solver gewählte Kacheln werden nach Abschluss wie manuell ausgewählte hervorgehoben.

## `route_cleanup.py` – Sackgassen-Bereinigung

Läuft nach jeder erfolgreichen Routenberechnung (beide Solver-Pfade), bevor die finale `Route` gebaut wird.

**Warum nötig:** Beide Solver wählen pro Kachel einen einzelnen Eingangspunkt und routen gezielt dorthin. Durchquert die Route dieselbe Kachel später ohnehin nochmal (z. B. weil der Weg zu einer anderen Kachel zufällig hindurchführt), war der frühere Extra-Abstecher – rein, exakt derselbe Weg zurück – reine Verschwendung.

**`remove_redundant_spurs(datastore, path, target_tile_ids, protected_nodes)`:**
1. Durchsucht die Knotenfolge nach Schleifen: Positionen `(j, i)` mit `path[j] == path[i]` (Route kehrt zu einem bereits besuchten Knoten zurück).
2. Für jede Schleife: welche Zielkacheln werden durch Knoten *innerhalb* der Schleife abgedeckt? Werden alle davon **auch außerhalb** der Schleife abgedeckt (vorher oder nachher), ist die komplette Schleife beweisbar überflüssig → wird herausgeschnitten.
3. Läuft bis zum Fixpunkt (mehrere Schleifen können sich überlappen/verschachteln; nach jeder Entfernung verschieben sich Indizes, daher Neustart des Scans).
4. **Schutzmechanismen:** Waypoint-Knoten und Start/Ende (`protected_nodes`) dürfen nie innerhalb einer entfernten Schleife verschwinden. Der allerletzte Knotenindex wird nie als Schleifenende zugelassen – sonst würde eine Rundtour (Start == Ende) beim ersten Durchlauf komplett auf ihren Startpunkt kollabieren, da Start und Ende dann derselbe Knoten sind.

**Verifiziert:** reale 35-Kacheln-Route von 65,8 km auf 55,4 km verkürzt (-15%) bei vollständig erhaltener Kachelabdeckung.

## `scoring.py` – Kachel-Priorisierung

Beantwortet: "Welche fehlende Kachel bringt am meisten fürs größte Quadrat / die größte zusammenhängende Fläche?"

- **`score_cluster_candidates()`:** Union-Find über alle besuchten Kacheln liefert Cluster-Größen. Für jede fehlende Rand-Kachel:
  - *Brücken-Bonus* (dominiert den Score, `BRIDGE_WEIGHT=1000`): Zugewinn über das hinaus, was das bloße Anschließen an den größten Nachbar-Cluster bringen würde – nur > 0, wenn die Kachel zwei *getrennte* Cluster verbindet.
  - *Kompaktheits-Wert* (1-4): Anzahl bereits besuchter Nachbarn – Lücken/Dellen füllen (3-4) ist wertvoller als den Rand nur nach außen zu schieben (1).
  - *Warum diese Aufteilung:* Ohne sie wächst jede normale Randkachel den Cluster nur um +1 – der komplette Rand hätte praktisch denselben Score, keine sinnvolle Abstufung.
- **`find_best_square_completion()`:** Für jede Zone (`compute_zones()`) und jede Quadratgröße oberhalb des aktuellen **globalen** Max-Square-Rekords: findet via Integral-Image (O(1) Rechteck-Summen) das Fenster mit der geringsten Anzahl fehlender Kacheln, die zusätzlich eine **zusammenhängende** Gruppe bilden müssen (4-Nachbarschafts-Check).
  - *Warum global statt pro Zone:* eine winzige, geografisch entfernte Zone (z. B. eine einzelne Auslandsaktivität) hat oft einen viel kleineren eigenen "Rekord" – lokal verglichen sähe jede Verbesserung dort fälschlich relevant aus.
  - *Warum zusammenhängend:* eine Tour deckt ohnehin 50-100 Kacheln ab; eine Handvoll verstreuter Einzelkacheln als "Ziel" ist keine sinnvolle Fahrempfehlung, ein zusammenhängender Flicken schon.

## Bekannte Einschränkungen / bewusste Kompromisse (Zusammenfassung)

- Abbiegeverbote werden seit der `osmnx`-Migration nicht mehr berücksichtigt.
- Turnaround-Cost ist eine Heuristik, kein exakter Constraint (bestehende Einschränkung aus dem Original-Projekt).
- OR-Tools-Pfad (>15 Kacheln) nutzt nur einen Eingangspunkt pro Kachel und ignoriert Einbahnstraßen zwischen weit entfernten Wegpunkten.
- Schotter-Freigabe wirkt nur lokal (Standard-Radius 1,5 km um die Kachel) – bei sehr abgelegenen Kacheln kann eine größere Downloadregion/Radius nötig sein, damit die Verbindung zum restlichen Straßennetz gefunden wird.

## Fahrmodi (`pyroutelib3.TYPES`)

| Modus | Netzwerk | Charakteristik |
|---|---|---|
| `roadcycle` | bike | Straßen/Radwege bevorzugt, unbefestigte Tracks/Pfade ausgeschlossen (außer asphaltiert) |
| `gravelbike` | bike | Wie roadcycle, aber Tracks/Pfade/Bridleways ausdrücklich erwünscht statt ausgeschlossen |
| `road_foot` | walk | Fußgänger, bevorzugt befestigte Wege |
| `foot` | walk | Fußgänger, alle Wegtypen etwa gleich gewichtet |
| `trail` / `trail2` | walk | Fußgänger, Trails/Tracks stark bevorzugt, Straßen gemieden |
