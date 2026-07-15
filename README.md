# Route Tiles

[TOC]

## Motivation

This project computes routes for tile-hunting: exploring/covering as many map "tiles" as possible
by bike or on foot, the way [statshunters](https://www.statshunters.com) or
[veloviewer](https://veloviewer.com) track them. You pick a start point and either the tiles you
want to ride through or a rough distance budget, and the app computes a real, rideable/walkable
route through OpenStreetMap roads and paths.

This is a personal fork of [BenoitBouillard/route-tiles](https://github.com/BenoitBouillard/route-tiles),
with a modernized routing engine, a reworked GUI, and a number of bug fixes and new features - see
`UPDATES.md` for the full history and `TODO.md` for what's still open.

It's built as a local, single-user tool: no accounts, no authentication, meant to be run on your
own machine (or a machine you trust) rather than exposed publicly as-is.

## Features

- Two ways to compute a route:
  - **Manual**: click the exact tiles you want to visit on the map.
  - **Distance target**: give a start point and a rough distance budget (e.g. "~40 km from here")
    and let the solver pick which not-yet-visited tiles are worth riding through.
- Five travel modes (Roadcycle, Gravel bike, Road by foot, Foot, Trail), each with its own
  road-type preferences.
- Automatic fallback to unpaved surfaces for a tile only reachable via gravel/track, with an
  explicit per-tile opt-in dialog.
- Two routing solvers, chosen automatically based on how many tiles are involved: an exact
  algorithm for small selections, and a Google OR-Tools based heuristic for larger ones (with an
  estimated search time and a "Precision mode"/"Turbo mode" indicator shown in the UI).
- Import your visited tiles from a [statshunters.com](https://statshunters.com) share link, with
  an activity-type filter (Ride/Run/...), a cluster overlay, and a "which tiles would grow your
  biggest square" recommendation.
- A **Demo** toggle (next to the language switcher) to try the whole app with a bundled sample
  dataset - no Statshunters account needed.
- Save, rename, duplicate, merge, split, and filter (by regex) multiple computed routes locally in
  the browser, and download any of them as GPX.
- English, French and German UI.

## Installation guide

Requirements: Python 3.9+.

```shell
git clone https://github.com/GoSo12/route-tiles.git
cd route-tiles
pip install -r requirements.txt
```

To also run the test suite (see [Testing](#testing) below):

```shell
pip install -r requirements-dev.txt
```

To pull in updates from this fork later:

```shell
git pull
```

## Running the server

```shell
python route-tiles-server.py
```

```shell
serving at port 8000
```

Change the port with `--port` (or `-p`):

```shell
python route-tiles-server.py --port 80
serving at port 80
```

## User interface

Once the server is running, open [http://localhost:8000](http://localhost:8000) in a browser (same
machine as the server). All map/tile selections, saved routes, and settings are stored locally in
the browser (`localStorage`) - refreshing or reopening the page keeps your state.

The panel on the right is organized into collapsible sections: **Map data** (Statshunters
import/demo mode), **Transport & route** (mode, turnaround cost, start/end/waypoints), **Target:
choose tiles** (manual selection or distance target), and **Saved routes**.

### Map data: importing your visited tiles

Create a sharelink on [statshunters.com/share](https://statshunters.com/share) (looks like
`https://www.statshunters.com/share/abcdef123456`), paste it into the "Sharelink from
statshunters.com" field and click "Load from statshunters". Activities are cached locally after the
first import - "Load from statshunters" again re-fetches from Statshunters if new activities were
added since; switching the "Activity type" dropdown re-filters the already-cached data instantly.

Once tiles are loaded, the map also shows:
- your existing cluster of visited tiles (orange outline),
- your current biggest square (blue outline), and
- which not-yet-visited tiles (purple) would grow that square to the next size, plus how many
  tiles that would take.

Don't have a Statshunters account? Flip the **Demo** switch (top of the page, next to the language
selector) to try everything with a bundled sample dataset instead.

### Transport & route

Pick a travel mode:

- **Roadcycle**: paved roads and cycle paths only, avoids major roads where possible.
- **Gravel bike**: happy on unpaved tracks/paths, actively prefers them over busy roads.
- **Road by foot**: paved roads/paths only, on foot.
- **Foot**: any path, on foot, no surface preference.
- **Trail**: prefers unpaved paths/tracks, on foot.

**Turnaround cost** adds an extra cost for out-and-back turnarounds in the route, in case you'd
rather add some detour distance than backtrack on the same road. This only affects the exact
solver (small tile counts) - it doesn't always find the true optimum when a nonzero turnaround
cost is set, since that turns the search into a genuinely harder problem than plain shortest-path.

Start position is mandatory; without an end position, the route loops back to the start. Click
"Start"/"End" then click the map to place a marker; markers can be dragged, swapped, or removed.
Waypoints (points the route must pass through) work the same way via "Add waypoint".

### Target: choose tiles

**Manual**: click tiles on the map to select/deselect them. Above ~15 tiles the app automatically
switches from the exact solver to the faster OR-Tools heuristic (shown next to the tile count) -
computation time grows quickly with tile count for the exact solver, especially in areas with many
road intersections, so avoid selecting a huge number of tiles at once if you want a quick result.

**Distance target**: instead of picking tiles yourself, give a distance budget and the solver picks
which reachable, not-yet-visited tiles to string together within that budget.

If a selected tile has no entry point reachable under the current mode's normal surface rules (e.g.
a Roadcycle route needing to pass through a gravel-only area), a dialog offers to allow gravel/
unpaved surfaces for that specific tile.

### Managing computed/saved routes

Once a route is computed, download it as GPX directly, or give it a name and add it to "Saved
routes" for later. Saved routes support:

- Rename, duplicate, remove
- Merge two routes into one, or splice a section of one route into another
- Split a route at a clicked point
- Undo up to 10 actions
- Filter the list by a regex against route names (e.g. `^Ride`, `[0-9]$`)

## Testing

```shell
pip install -r requirements-dev.txt
pytest
```

Covers tile-grid math, scoring/cluster computation, Statshunters URL validation and parsing, search
time estimation, and the OR-Tools cost-graph safety checks - see `tests/`.

## Project documentation

- **`TODO.md`** - open items.
- **`UPDATES.md`** - running changelog, including root-cause writeups for bugs found/fixed.
- **`DOCUMENTATION.md`** - architecture and rationale for how things are built.

## License

MIT, see `LICENSE`. Originally by [Benoit Bouillard](https://github.com/BenoitBouillard).
