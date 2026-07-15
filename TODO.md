# TODO

Offene Punkte, geordnet nach Themenblock. Erledigtes wird nach `UPDATES.md` verschoben, nicht hier gestrichen liegen gelassen.

## 1. Kachel-Darstellung an squadrats.com angleichen ✅ erledigt

Vom Nutzer außerhalb dieser Session umgesetzt.

## 2. Demo-Modus ✅ erledigt

Siehe `UPDATES.md`. Bundled Beispieldaten (`demo_data/`) + "Try it with demo data"-Button, funktioniert ohne Statshunters-Account/Import.

## 3. Komplettes Durchtesten des Codes: Funktionalität, Performance, Sicherheit

Kernpunkte abgearbeitet (siehe `UPDATES.md` für Details):
- ✅ **Sicherheit:** systematischer Code-Durchgang – SSRF- und Verzeichnis-Escape-Lücke über den `url`-Parameter gefunden und behoben, toter aber gefährlicher Upload-Code entfernt, Session-IDs auf CSPRNG umgestellt. Mit echten Angriffs-Payloads gegen den laufenden Server verifiziert, Regressionstests in `tests/test_statshunters.py`.
- ✅ **Orienteering-Abbruch-Test:** mit echten Statshunters-Daten durchgeführt – verhält sich korrekt, identisch zum bereits verifizierten manuellen/OR-Tools-Pfad.
- ✅ **Regressionstest-Infrastruktur:** `tests/` mit `pytest` (45 Tests) für Kachel-Mathematik, Scoring, Statshunters-Parsing/URL-Validierung, Zeitschätzung, OR-Tools-Kostenberechnung – ersetzt die bisherigen Ad-hoc-`curl`-Aufrufe für die schnell testbaren, deterministischen Teile des Codes.
- ✅ **Performance:** mit echten Daten gemessen statt geschätzt – reine Berechnungsfunktionen unkritisch (<25 ms), OR-Tools skaliert vorhersagbar (~1 s/Kachel), konkreter Befund beim exakten Solver (Laufzeit hängt stark von der Eintrittspunkt-Dichte pro Kachel ab, nicht nur von der Kachelanzahl – Zeitschätzung kann dafür daneben liegen), OSM-Download als größter Hebel identifiziert (bereits behoben, siehe "Kacheln fürs größte Quadrat"-Eintrag).

**Noch offen:** die Testsuite deckt bewusst die schnellen, deterministischen Teile ab (Mathematik/Scoring/Parsing/Kostenberechnung), nicht aber eine vollständige End-to-End-Matrix aus allen Fahrmodi × allen Solver-Pfaden mit echten OSM-Daten (dafür bräuchte es lang laufende Integrationstests, die nicht gut in eine schnelle `pytest`-Suite passen) – bei Bedarf gezielt nachziehen, falls ein konkreter Verdacht auf ein Problem in einem bestimmten Modus/Pfad aufkommt.

## 4. Modernisierungs-Audit (Abgleich mit den ursprünglichen Empfehlungen vom Sitzungsbeginn)

Zu Beginn dieses Projekts wurden folgende Technologien empfohlen – Status:

| Empfehlung | Status |
|---|---|
| OSMnx + NetworkX statt `pyroutelib3` | ✅ umgesetzt |
| Google OR-Tools für große Kachelmengen | ✅ umgesetzt |
| Statshunters als Datenquelle | ✅ umgesetzt (bestehender Import genutzt) |
| OSRM/Valhalla (State-of-the-Art-Routing) | ❌ verworfen (kein Docker/Homebrew verfügbar) – bei geänderter Umgebung neu bewerten |
| mercantile für Tile-Mathematik | ✅ umgesetzt (siehe `UPDATES.md`) |

Die konkret gefundenen Alt-Abhängigkeiten/Code-Reste sind mittlerweile abgearbeitet (siehe `UPDATES.md`): `pyroutelib3.py` auf die Gewichtstabellen reduziert, `not_update_routing` entfernt, `fastkml` auf 1.4.x portiert, Frontend-Libs (jQuery/Leaflet/Bootstrap/jquery.i18n) auf die neuesten rückwärtskompatiblen Versionen gehoben.

**Noch offen, bewusst zurückgestellt:**
- **Bootstrap 5 + jQuery-Entfernung**: Major-Upgrade mit Breaking Changes (`data-toggle`/`data-target` → `data-bs-toggle`/`data-bs-target`, neue JS-API für Modal/Dropdown/Collapse ohne jQuery). Auf Nutzerwunsch zurückgestellt zugunsten der risikoärmeren Minor/Patch-Updates – bei Bedarf als eigener, dedizierter Umbau angehen.
- **leaflet-omnivore 0.3.1**: von Mapbox seit Jahren nicht weiterentwickelt, aber keine neuere Version verfügbar – Ersatz würde einen eigenen KML-Parser oder eine andere Bibliothek erfordern, nicht nur einen Versionsbump.
- **`do_route_with_crossing_zone`** (exakter Algorithmus, tilesrouter.py): strukturell geprüft und jetzt mit einem Docstring versehen, der den Algorithmus (A*-artige Suche über (Knoten, Restmenge-Zonen)-Zustände) erklärt. Bewusst nicht umgeschrieben – funktioniert nachweislich korrekt (mehrfach in dieser Sitzung durch reale Bugs verifiziert), ein Umbau ohne konkreten treibenden Bug wäre unnötiges Regressionsrisiko für eine dicht verschachtelte, aber funktionierende kombinatorische Suche.

## 5. Nach GitHub committen

Commit auf ein eigenes GitHub-Repository sichern (`origin` zeigt aktuell auf das Original-Repo `BenoitBouillard/route-tiles`, dort besteht kein Schreibzugriff – eigener Fork/eigenes Repo muss zuerst angelegt werden, siehe frühere Rückstellung dieser Entscheidung in der Sitzung).
