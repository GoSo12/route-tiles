# TODO

Offene Punkte, geordnet nach Themenblock. Erledigtes wird nach `UPDATES.md` verschoben, nicht hier gestrichen liegen gelassen.

## 1. Komplettes Durchtesten des Codes

Systematischer Test-Durchgang über den gesamten Code (nicht nur Einzelfall-Stichproben wie bisher): alle Fahrmodi, alle Solver-Pfade (exakt/OR-Tools/Orienteering), Schotter-Freigabe, Sackgassen-Bereinigung, Scoring-Funktionen, Statshunters-Import – idealerweise mit einer nachvollziehbaren Sammlung von Testfällen/Regressionstests statt Ad-hoc-`curl`-Aufrufen wie bisher in der Session.

- ✅ Erledigt: `/abort_route` gegen eine länger laufende OR-Tools-Berechnung (20 Kacheln) getestet. Dabei einen echten Bug gefunden und behoben (fehlende `self._exit`-Prüfung nach `solve_tile_route()` – Abbruch wurde ignoriert, Route lief immer zu Ende), siehe `UPDATES.md`. Noch offen: derselbe End-to-End-Test für den Orienteering-Pfad (`/start_orienteering`) steht noch aus (dafür wird eine echte Statshunters-URL benötigt, ein leerer Testaufruf schlägt fehl).

## 2. Modernisierungs-Audit (Abgleich mit den ursprünglichen Empfehlungen vom Sitzungsbeginn)

Zu Beginn dieses Projekts wurden folgende Technologien empfohlen – Status:

| Empfehlung | Status |
|---|---|
| OSMnx + NetworkX statt `pyroutelib3` | ✅ umgesetzt |
| Google OR-Tools für große Kachelmengen | ✅ umgesetzt |
| Statshunters als Datenquelle | ✅ umgesetzt (bestehender Import genutzt) |
| OSRM/Valhalla (State-of-the-Art-Routing) | ❌ verworfen (kein Docker/Homebrew verfügbar) – bei geänderter Umgebung neu bewerten |
| mercantile für Tile-Mathematik | ✅ umgesetzt (siehe `UPDATES.md`) |

**Konkret gefundene, mehrere Jahre alte Abhängigkeiten/Code-Reste, die noch modernisiert werden sollten:**

- **`pyroutelib3.py`**: Nur noch die `TYPES`-Gewichtstabellen werden genutzt, der komplette OSM-Parsing-/Datastore-Code (Live-Download von der OSM-Editier-API, `Datastore`-Klasse) ist toter Code seit der `osmnx`-Migration – könnte entfernt/auf die Tabellen reduziert werden.
- **`fastkml<1.0`** (in `requirements.txt`): bewusst auf die alte, nicht mehr weiterentwickelte API-Generation gepinnt, weil `statshunters.py`s KML-Erzeugung die alte, klassische API nutzt. Sauberer wäre eine Portierung auf die aktuelle `fastkml`-API.
- **Frontend-Abhängigkeiten** (alle via CDN eingebunden, Versionen geprüft):
  - Bootstrap 4.5.2 (Release 2020, Bootstrap 4 ist inzwischen EOL, aktuell wäre 5.x)
  - jQuery 3.4.1 (Release 2019, aktuell wäre 3.7.x; jQuery insgesamt gilt in modernem Frontend als Altlast)
  - jquery.i18n 1.0.7 (Wartungsstatus unklar)
  - Leaflet 1.6.0 (Release 2020, aktuell wäre 1.9.x)
  - leaflet-omnivore 0.3.1 (von Mapbox seit Jahren nicht mehr weiterentwickelt)
- **`tile.py`**: `not_update_routing`-Buchführung war für das alte, lazy-ladende `pyroutelib3.Datastore`-Modell gedacht (verhindert doppeltes Verarbeiten bei wiederholtem Nachladen). Seit `osmnx` die Region komplett im Voraus lädt, ggf. nicht mehr nötig – noch nicht geprüft, ob das gefahrlos entfernt werden kann.
- **`do_route_with_crossing_zone`** (exakter Algorithmus, tilesrouter.py): unverändert der ursprüngliche, mehrere Jahre alte Suchalgorithmus des Original-Projekts. Funktioniert für kleine Kachelmengen weiterhin korrekt (nutzt inzwischen auch die korrigierte `segment_distance`), aber strukturell nicht überarbeitet.
