"""Distance-budgeted route planning: "starting here, with roughly N km to
ride, which tiles should I collect?" - as opposed to ortools_router.py and
tilesrouter.py's do_route_with_crossing_zone, which both take a fixed set of
must-visit tiles and minimize distance.

This is a classic Orienteering Problem (maximize collected prize subject to
a travel budget), which OR-Tools supports directly: a distance Dimension
caps total route length, and each candidate tile is an *optional* stop
(AddDisjunction) with a penalty for skipping it equal to its prize - the
solver then picks whichever subset of tiles yields the most prize without
exceeding the budget.
"""
import networkx as nx
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from ortools_router import _cost_graph, _tile_representative_node
from scoring import ADJOINING
from tile import tile_from_coord, Tile

UNREACHABLE_PENALTY_M = 10 ** 9
# Scales prize onto the same numeric scale as distance costs (meters).
# Deliberately large: the objective OR-Tools actually minimizes is
# (distance driven + penalty for every skipped tile), which is subtly NOT
# the same as "maximize tiles collected within the budget" - with a small
# scale, a tile only "pays for" a small detour, so the solver stops early
# and leaves budget unused once the cheap wins are gone. Since the hard cap
# (AddDimension below) is what actually keeps the route within budget, the
# prize scale just needs to be large enough that skipping a reachable tile
# is almost always worse than the extra distance to get it - approximating
# "use the budget, maximize what you collect" rather than "collect cheaply".
PRIZE_SCALE = 8000

# ~1km per tile at the zoom level this project's tiles use, so this is a
# rough, deliberately generous tiles-per-km conversion for sizing the
# candidate search box.
KM_PER_TILE = 1.0


def _generate_candidates(start_loc, visited_tiles, budget_km, max_candidates=150):
    """Every not-yet-visited tile within reach of the budget, scored by how
    much it would grow the existing connected/visited area.

    Deliberately simple, static scoring (not scoring.py's full bridge-bonus
    formula): base prize 1 for any missing tile in range, +2 per already
    visited neighbor (so tiles touching the existing cluster are far more
    attractive than isolated ones, encouraging contiguous growth) - and
    riding to a cluster of adjacent candidates costs little extra distance
    once you're in the area anyway, so the route naturally sweeps connected
    patches rather than scattering.
    """
    visited_set = set(tuple(int(v) for v in t.split('_')) for t in visited_tiles)
    start_x, start_y = tile_from_coord(*start_loc, output="list")

    # A loop route has to reach a tile *and* come back - budget/2 in a
    # dead-straight line is already generous, real road distance and the
    # need to loop through several stops shrink the true reachable area
    # further. Erring smaller here is cheap (just fewer candidates
    # considered); erring larger wastes candidate slots on tiles that could
    # never be reached within budget anyway.
    radius_tiles = int(budget_km * 0.35 / KM_PER_TILE) + 2

    scored = {}
    for dx in range(-radius_tiles, radius_tiles + 1):
        for dy in range(-radius_tiles, radius_tiles + 1):
            xy = (start_x + dx, start_y + dy)
            if xy in visited_set:
                continue
            visited_neighbors = sum(
                1 for adx, ady in ADJOINING
                if (xy[0] + adx, xy[1] + ady) in visited_set
            )
            prize = 1 + visited_neighbors * 2
            tile_dist = (dx * dx + dy * dy) ** 0.5
            scored["{}_{}".format(*xy)] = (prize, tile_dist)

    # Cap to the most promising candidates so the solver's landmark count
    # stays in the range already proven to work (ortools_router.py handled
    # ~130 tiles comfortably). Rank by prize *density* (prize per tile of
    # distance from start), not raw prize - a high-prize tile far outside
    # what the budget could ever reach would otherwise crowd out closer,
    # actually-collectible tiles.
    ranked = sorted(
        scored.items(),
        key=lambda kv: -kv[1][0] / (1 + kv[1][1]),
    )
    return {tid: prize for tid, (prize, _) in ranked[:max_candidates]}


def solve_orienteering_route(datastore, start_node, end_node, candidates, tile_points,
                              budget_km, time_limit_s=60):
    """candidates: {tile_id: prize}. tile_points: {tile_id: Tile}, already
    processed (tile.get_entry_points(datastore) already called by the
    caller - see ortools_router._tile_representative_node for why this
    must not be redone here). Finds a route from start_node to end_node
    visiting whichever subset of candidate tiles maximizes total collected
    prize, subject to total route length <= budget_km.

    Returns (status, node_path, visited_tile_ids).
    """
    tile_ids = list(candidates.keys())
    landmarks = [start_node, end_node] + [
        _tile_representative_node(tile_points[t]) for t in tile_ids
    ]
    n = len(landmarks)
    cost_graph = _cost_graph(datastore)

    matrix = [[0] * n for _ in range(n)]
    for i, src in enumerate(landmarks):
        lengths = nx.single_source_dijkstra_path_length(cost_graph, src, weight="cost")
        for j, dst in enumerate(landmarks):
            if i == j:
                continue
            matrix[i][j] = lengths.get(dst, float("inf"))

    manager = pywrapcp.RoutingIndexManager(n, 1, [0], [1])
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        d = matrix[from_node][to_node]
        if d == float("inf"):
            return UNREACHABLE_PENALTY_M
        return int(d * 1000)  # km -> meters

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    routing.AddDimension(
        transit_callback_index,
        0,  # no slack
        int(budget_km * 1000),  # hard cap, in meters
        True,  # cumulative distance starts at 0
        "Distance",
    )

    for idx, t in enumerate(tile_ids):
        node_index = manager.NodeToIndex(2 + idx)
        routing.AddDisjunction([node_index], int(candidates[t] * PRIZE_SCALE))

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_parameters.time_limit.FromSeconds(time_limit_s)

    solution = routing.SolveWithParameters(search_parameters)
    if not solution:
        return "no_route", [], []

    order = []
    index = routing.Start(0)
    while not routing.IsEnd(index):
        order.append(manager.IndexToNode(index))
        index = solution.Value(routing.NextVar(index))
    order.append(manager.IndexToNode(index))

    visited_tile_ids = [tile_ids[i - 2] for i in order if i >= 2]

    full_path = []
    for i in range(len(order) - 1):
        a = landmarks[order[i]]
        b = landmarks[order[i + 1]]
        segment = nx.shortest_path(cost_graph, a, b, weight="cost")
        if full_path and full_path[-1] == segment[0]:
            full_path.extend(segment[1:])
        else:
            full_path.extend(segment)

    return "success", full_path, visited_tile_ids


def plan_orienteering_route(datastore, start_loc, visited_tiles, budget_km, time_limit_s=60):
    """Top-level entry point: preload the region, generate candidates, solve.
    end_loc == start_loc (a loop) - the common case for "ride out from home
    and back".
    """
    candidates = _generate_candidates(start_loc, visited_tiles, budget_km)

    # Reuse/populate datastore.tile_cache (not a fresh Tile() per call) -
    # a repeat search in the same session would otherwise re-run
    # get_entry_points() on an already-split graph and corrupt
    # edge_lengths/edge_shapes for tiles processed before (see
    # OsmnxDatastore.tile_cache).
    tile_points = {}
    for t in candidates:
        if t not in datastore.tile_cache:
            datastore.tile_cache[t] = Tile(t)
        tile_points[t] = datastore.tile_cache[t]
    datastore.preload_region(
        [start_loc] + [(t.lat, t.lon) for t in tile_points.values()],
        margin_km=3,
    )

    # Candidates with no entry point under the current mode's strict weights
    # (e.g. only reachable via a track roadcycle excludes) simply drop out
    # of consideration here - this planner has no per-tile gravel opt-in
    # dialog the way the manual tile-selection flow does.
    reachable = {}
    for t, tile in tile_points.items():
        tile.get_entry_points(datastore)
        if tile.entryNodeId:
            reachable[t] = candidates[t]
    candidates = reachable

    start_node = datastore.find_node(*start_loc)
    return solve_orienteering_route(
        datastore, start_node, start_node, candidates, tile_points, budget_km, time_limit_s
    )
