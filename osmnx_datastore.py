"""Drop-in replacement for pyroutelib3.Datastore, backed by osmnx/OSM extracts
instead of live per-tile downloads from the OSM editing API.

tilesrouter.py and tile.py only ever touch the following surface of a
Datastore, so that is exactly what this class reproduces:

- .rnodes[node_id] -> (lat, lon)                       (read AND written directly by tile.py)
- .routing[node_id][neighbor_id] -> weight              (read AND written directly by tile.py)
- .forbiddenMoves / .mandatoryMoves                      (turn restrictions - see limitation below)
- .node_lat_lon(node_id)
- .find_node(lat, lon)
- .get_area(lat, lon) / .get_area_rect(lat1, lon1, lat2, lon2)

Known simplification: turn restrictions (forbiddenMoves/mandatoryMoves) are
left empty. osmnx builds its graph from ways only, not from OSM turn
restriction relations, and pyroutelib3's own handling of them was already a
rough approximation. Re-adding it would mean parsing restriction relations
separately - out of scope for this migration.
"""
import math
from pathlib import Path

import networkx as nx
import osmnx as ox

from pyroutelib3 import TYPES
from utils import distance

# Reused as the "gravel/unpaved OK" fallback profile: much more permissive
# about track/path/bridleway than roadcycle's own weight table.
GRAVEL_FALLBACK_WEIGHTS = TYPES["trail"]["weights"]

MODE_NETWORK_TYPE = {
    "roadcycle": "bike",
    "gravelbike": "bike",
    "road_foot": "walk",
    "foot": "walk",
    "trail": "walk",
    "trail2": "walk",
}

EQUIVALENT_HIGHWAY = {
    "motorway_link": "motorway",
    "trunk_link": "trunk",
    "primary_link": "primary",
    "secondary_link": "secondary",
    "tertiary_link": "tertiary",
    "minor": "unclassified",
    "pedestrian": "footway",
    "platform": "footway",
}

GRID_CELL_DEG = 0.2  # region cache granularity


class OsmnxDatastore:
    def __init__(self, transport, cache_dir="osmnx_cache", margin_km=3):
        self.transport = transport
        self.type = TYPES[transport].copy()
        self.network_type = MODE_NETWORK_TYPE.get(transport, "bike")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.margin_km = margin_km

        self.routing = {}
        self.rnodes = {}
        self.forbiddenMoves = {}
        self.mandatoryMoves = {}
        # (u, v) -> [(lat, lon), ...] real curve points between the two nodes,
        # only present where osmnx's graph simplification merged a chain of
        # shape points into one edge. Without this, a route reconstructed
        # from bare node coordinates would cut straight across curves/bends.
        self.edge_shapes = {}
        # (u, v) -> real curve length in km (osmnx precomputes this from the
        # true geometry, in meters) - straight endpoint-to-endpoint distance
        # would underestimate curvy roads and could skew route selection.
        self.edge_lengths = {}

        # tile_id -> Tile, already processed (get_entry_points() already
        # called). Lives here, not on the per-search MyRouter/OrienteeringRunner
        # instance, so it survives across repeated searches within the same
        # session (e.g. the user adjusts the end point/waypoints and
        # re-searches with the same tile selection) - exactly as long as
        # self.routing/self.rnodes themselves do, since a cached Tile's
        # entry-point node ids only make sense against this specific graph.
        # Without this, a second search would build fresh Tile objects and
        # call get_entry_points() again on an already-split graph, handing
        # out synthetic node ids (tile uid + a counter starting over at 0)
        # that collide with ones already in use for different physical
        # points - silently corrupting edge_lengths/edge_shapes for
        # whichever location the id was first assigned to (the "wilde
        # Sprünge" bug, confirmed to recur through exactly this path).
        self.tile_cache = {}

        self._graph = nx.MultiDiGraph()
        self._loaded_cells = set()

    # ---- interface used by tilesrouter.py / tile.py ----

    def shape_between(self, u, v):
        """Intermediate (lat, lon) points of the real road curve between
        nodes u and v, excluding both endpoints. Empty list if the edge has
        no stored curve (already a straight segment) or doesn't exist.

        Checks both directions: shapes are recorded once, keyed by the
        original osmnx edge direction (u, v). The OR-Tools solver runs on an
        *undirected* cost graph (see ortools_router._cost_graph) and can
        therefore traverse a real one-way edge backwards - without this
        fallback, that specific hop would silently lose its curve and get
        drawn as a straight line cutting across the bend.
        """
        if (u, v) in self.edge_shapes:
            return self.edge_shapes[(u, v)]
        if (v, u) in self.edge_shapes:
            return list(reversed(self.edge_shapes[(v, u)]))
        return []

    def edge_length(self, u, v):
        """Real length (km) of the road between u and v, following its
        actual curve - not the straight-line distance between the two
        endpoint nodes. None if u/v aren't directly connected by a known
        osmnx edge (e.g. synthetic tile-entry nodes), in which case callers
        should fall back to plain haversine distance.

        Checks both directions (length is direction-independent) - see
        shape_between() for why the reverse direction can be the only one
        recorded.
        """
        if (u, v) in self.edge_lengths:
            return self.edge_lengths[(u, v)]
        return self.edge_lengths.get((v, u))

    def node_lat_lon(self, node):
        return self.rnodes[node]

    def get_area(self, lat, lon):
        self._ensure_region(lat, lon, lat, lon)

    def get_area_rect(self, lat1, lon1, lat2, lon2):
        self._ensure_region(lat1, lon1, lat2, lon2)

    def _is_routable(self, node):
        return any(w > 0 for w in self.routing.get(node, {}).values())

    def find_node(self, lat, lon):
        """Nearest node to (lat, lon) that's actually routable under the
        current mode - not just the geometrically nearest node in the raw
        graph, which can land on a node only reachable via a road type
        this mode's weight table excludes (e.g. a building-entrance node
        linked only by a footway, while routing in "roadcycle" mode).

        Found via a real reproduction: such a node has an empty entry in
        self.routing (degree 0 in the routing graph). Handed to the
        OR-Tools solver as a start/end/landmark node, it silently poisons
        the distance matrix (every pair involving it is "unreachable",
        which ortools_router.py only penalizes heavily instead of
        forbidding outright - see UNREACHABLE_PENALTY_M) - manifesting as
        either a crash ("No path between ...") when OR-Tools is forced to
        use it, or a nonsensical straight-line "shortcut" in the rendered
        route when it isn't. Searching outward for the nearest *routable*
        node instead fixes this at the source, the same way
        allow_gravel_near() already searches outward for gravel tiles.
        """
        self.get_area(lat, lon)
        node = int(ox.distance.nearest_nodes(self._graph, lon, lat))
        if self._is_routable(node):
            return node

        for radius_km in (0.15, 0.3, 0.6, 1.2, 2.5, 5.0):
            margin_deg = radius_km / 111.0
            self.get_area_rect(lat - margin_deg, lon - margin_deg,
                                lat + margin_deg, lon + margin_deg)
            best, best_dist = None, None
            for n, (n_lat, n_lon) in self.rnodes.items():
                if abs(n_lat - lat) > margin_deg or abs(n_lon - lon) > margin_deg:
                    continue
                if not self._is_routable(n):
                    continue
                d = distance((n_lat, n_lon), (lat, lon))
                if d > radius_km:
                    continue
                if best is None or d < best_dist:
                    best, best_dist = n, d
            if best is not None:
                return best

        # Nothing routable within 5km - fall back to the original
        # (unroutable) node so callers see the same failure they always
        # would have (e.g. ERR_NO_TILE_ENTRY_POINT downstream), rather than
        # a new exception raised from inside find_node() itself.
        return node

    def _highway_of(self, data):
        highway = data.get("highway", "")
        if isinstance(highway, list):
            highway = highway[0]
        return EQUIVALENT_HIGHWAY.get(highway, highway)

    def allow_gravel_near(self, lat, lon, radius_km=1.5):
        """Connect (lat, lon) to the existing routable network via the
        shortest possible detour through gravel/unpaved ways, instead of
        blanket-unlocking every such way within radius_km.

        Earlier version committed every excluded edge (track/path/etc.)
        within the radius directly into self.routing. For a tile in a
        well-connected area, even the smallest radius that found an entry
        point still unlocked hundreds of edges - a whole secondary network
        the tour solver then happily (ab)used as a shortcut for unrelated,
        distant legs of the journey, not just to reach this one tile
        (verified: same big multi-tile route produced only a single >0.5km
        jump in this area without gravel tiles, dozens with them).

        This version only ever searches the candidate gravel edges (never
        commits them), finds the shortest path from a point near (lat, lon)
        to the nearest node that already has a real (non-gravel) connection
        to the rest of the network, and commits *only that one path* - a
        single spur, not a shortcut network. radius_km just bounds how far
        the search is allowed to look; a larger radius no longer means a
        larger permanently-unlocked area.
        """
        candidates = {}
        for u, v, data in self._graph.edges(data=True):
            u_lat, u_lon = self.rnodes.get(u, (None, None))
            if u_lat is None or distance((u_lat, u_lon), (lat, lon)) > radius_km:
                continue

            highway = self._highway_of(data)
            if self.type["weights"].get(highway, 0):
                continue  # already allowed under the current profile - not a gravel candidate

            weight = GRAVEL_FALLBACK_WEIGHTS.get(highway, 0)
            if callable(weight):
                weight = weight(data)
            if weight <= 0:
                continue

            candidates[(u, v)] = weight

        if not candidates:
            return 0

        gravel_graph = nx.Graph()
        for (u, v), w in candidates.items():
            cost = distance(self.rnodes[u], self.rnodes[v]) / w
            if gravel_graph.has_edge(u, v):
                gravel_graph[u][v]["cost"] = min(gravel_graph[u][v]["cost"], cost)
            else:
                gravel_graph.add_edge(u, v, cost=cost)

        anchors = {n for n in gravel_graph.nodes()
                   if any(wt > 0 for wt in self.routing.get(n, {}).values())}
        if not anchors:
            return 0  # this radius doesn't reach anything already connected - caller should try a bigger one

        tile_node = min(gravel_graph.nodes(),
                         key=lambda n: distance(self.rnodes[n], (lat, lon)))

        lengths, paths = nx.single_source_dijkstra(gravel_graph, tile_node, weight="cost")
        reachable_anchors = [a for a in anchors if a in lengths]
        if not reachable_anchors:
            return 0
        path = paths[min(reachable_anchors, key=lambda a: lengths[a])]

        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            w = candidates.get((u, v), candidates.get((v, u)))
            self.routing.setdefault(u, {})
            self.routing.setdefault(v, {})
            self.routing[u][v] = max(self.routing[u].get(v, 0), w)
            self.routing[v][u] = max(self.routing[v].get(u, 0), w)

        return len(path) - 1

    def preload_region(self, points, margin_km=None):
        """Download/cache one region covering every (lat, lon) in `points`
        up front, so the many small get_area/get_area_rect calls that
        tile.get_entry_points makes per tile all become cache hits."""
        lats = [p[0] for p in points]
        lons = [p[1] for p in points]
        self._ensure_region(min(lats), min(lons), max(lats), max(lons),
                             margin_km=margin_km)

    # ---- internal ----

    def _cell_key(self, lat, lon):
        return (round(lat / GRID_CELL_DEG), round(lon / GRID_CELL_DEG))

    def _ensure_region(self, lat1, lon1, lat2, lon2, margin_km=None):
        margin_km = self.margin_km if margin_km is None else margin_km
        margin_deg = margin_km / 111.0
        north, south = max(lat1, lat2) + margin_deg, min(lat1, lat2) - margin_deg
        east, west = max(lon1, lon2) + margin_deg, min(lon1, lon2) - margin_deg

        cells_needed = set()
        lat = south
        while lat <= north + GRID_CELL_DEG:
            lon = west
            while lon <= east + GRID_CELL_DEG:
                cells_needed.add(self._cell_key(lat, lon))
                lon += GRID_CELL_DEG
            lat += GRID_CELL_DEG

        missing = cells_needed - self._loaded_cells
        if not missing:
            return

        bbox = (west, south, east, north)
        self._load_bbox(bbox)
        self._loaded_cells |= cells_needed

    def _load_bbox(self, bbox):
        west, south, east, north = bbox
        cache_file = self.cache_dir / "{}_{:.3f}_{:.3f}_{:.3f}_{:.3f}.graphml".format(
            self.transport, west, south, east, north)

        if cache_file.exists():
            g = ox.load_graphml(cache_file)
        else:
            g = ox.graph_from_bbox(bbox, network_type=self.network_type, simplify=True)
            ox.save_graphml(g, cache_file)

        self._merge_graph(g)

    def _merge_graph(self, g):
        self._graph = nx.compose(self._graph, g)

        for node, data in g.nodes(data=True):
            if node not in self.rnodes:
                self.rnodes[node] = (float(data["y"]), float(data["x"]))
            self.routing.setdefault(node, {})

        for u, v, data in g.edges(data=True):
            if "geometry" in data:
                # geometry runs u -> v (confirmed against osmnx's own
                # simplification output); drop the first/last point since
                # those duplicate the u/v node coordinates already in rnodes.
                coords = list(data["geometry"].coords)[1:-1]
                if coords:
                    self.edge_shapes[(u, v)] = [(lat, lon) for lon, lat in coords]

            if "length" in data:
                self.edge_lengths[(u, v)] = data["length"] / 1000.0

            highway = data.get("highway", "")
            if isinstance(highway, list):
                highway = highway[0]
            highway = EQUIVALENT_HIGHWAY.get(highway, highway)

            weight = self.type["weights"].get(highway, 0)
            if callable(weight):
                weight = weight(data)
            if weight <= 0:
                continue

            self.routing.setdefault(u, {})
            self.routing[u][v] = max(self.routing[u].get(v, 0), weight)
