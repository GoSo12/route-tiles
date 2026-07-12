"""OR-Tools based tile-route solver for large tile counts.

tilesrouter.do_route_with_crossing_zone tracks state as
(current road node, set of not-yet-visited tiles). That set has up to 2^N
subsets for N tiles, so it is only tractable for roughly N < 15-20 - it
explores every possible entry point per tile as part of the same search,
which is precise but explodes combinatorially.

This module trades that precision for scalability: each tile is reduced to
one representative point (nearest road node to its center), turning the
problem into a plain TSP with a fixed start/end - which Google OR-Tools
solves with bounded, predictable runtime even for ~100 stops via a
time-limited metaheuristic (guided local search), instead of an open-ended
combinatorial search.
"""
import time

import networkx as nx
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from tile import Tile
from tilesrouter import segment_distance
from utils import distance

UNREACHABLE_PENALTY_M = 10 ** 9


def _cost_graph(datastore):
    """Undirected graph with edge weight = real distance / mode preference,
    built from an OsmnxDatastore's already-loaded routing dict - reused for
    repeated Dijkstra distance-matrix queries below.

    Undirected on purpose: a directed graph occasionally strands a tile's
    representative node in a one-way pocket that's reachable but not
    reversible, which contradicts the distance matrix during path
    reconstruction. At the "roughly which order to visit tiles in" scale
    this solver operates at, ignoring one-way restrictions between distant
    landmarks is an acceptable trade - the per-mode road-type preference
    weighting (the actual "prefer real roads over trails" behavior) still
    applies either way.
    """
    g = nx.Graph()
    g.add_nodes_from(datastore.rnodes.keys())
    for u, neighbors in datastore.routing.items():
        for v, weight in neighbors.items():
            if weight <= 0:
                continue
            cost = segment_distance(datastore, u, v) / weight
            if g.has_edge(u, v):
                g[u][v]["cost"] = min(g[u][v]["cost"], cost)
            else:
                g.add_edge(u, v, cost=cost)
    return g


def _tile_representative_node(datastore, tile_id):
    """One real, routable point per tile - reuses the existing (proven)
    entry-point detection instead of a naive nearest-node lookup, which can
    land on a node with no valid edges for the current mode (e.g. only
    reachable via a road type this mode's weight table excludes).

    Callers (MyRouter._run) already validate every tile has at least one
    entry point - with gravel relaxation applied first for tiles the user
    opted into - before ever reaching this solver, so entryNodeId is
    guaranteed non-empty here. No silent fallback to an unroutable nearest
    node: if this ever fires, something upstream skipped that check and
    should fail loudly rather than produce a bad route.
    """
    tile = Tile(tile_id)
    tile.get_entry_points(datastore)
    return min(tile.entryNodeId, key=lambda c: distance(c.latlon, (tile.lat, tile.lon))).nodeId


def _two_opt(order, matrix, time_limit_s=20):
    """Classic 2-opt local search on the landmark visiting order, with the
    first and last stop (start/end) held fixed.

    OR-Tools' own guided local search already tries similar moves, but under
    a shared time budget with everything else it has to do for a large
    instance - it can time out before untangling every crossing, leaving the
    tour dipping back into the same neighborhood repeatedly from unrelated
    directions. Since this operates on the small, already-computed landmark
    distance matrix (not the full road graph), a full pass is cheap even for
    ~100 tiles, so it is worth doing as a dedicated, focused clean-up on top
    of whatever OR-Tools already found - not a replacement for it.
    """
    order = list(order)
    n = len(order)
    start_time = time.time()
    improved = True
    while improved and (time.time() - start_time) < time_limit_s:
        improved = False
        for i in range(1, n - 1):
            a = order[i - 1]
            b = order[i]
            for j in range(i + 1, n - 1):
                c = order[j]
                d = order[j + 1]
                delta = (matrix[a][c] + matrix[b][d]) - (matrix[a][b] + matrix[c][d])
                if delta < -1e-9:
                    order[i:j + 1] = order[i:j + 1][::-1]
                    b = order[i]
                    improved = True
            if time.time() - start_time > time_limit_s:
                break
    return order


def solve_tile_route(datastore, start_node, end_node, tile_ids, waypoint_nodes=None, time_limit_s=30):
    """Find a route visiting one representative point per tile (plus any
    mandatory waypoint nodes), starting at start_node and ending at end_node.

    Returns (status, node_path) in the same shape as
    tilesrouter.MyRouter.do_route_with_crossing_zone:
    ("success"/"no_route", [node_id, ...]).
    """
    landmarks = (
        [start_node, end_node]
        + list(waypoint_nodes or [])
        + [_tile_representative_node(datastore, t) for t in tile_ids]
    )
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
        return int(d * 1000)  # km -> meters (OR-Tools wants integer costs)

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

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
        return "no_route", []

    order = []
    index = routing.Start(0)
    while not routing.IsEnd(index):
        order.append(manager.IndexToNode(index))
        index = solution.Value(routing.NextVar(index))
    order.append(manager.IndexToNode(index))

    order = _two_opt(order, matrix)

    full_path = []
    for i in range(len(order) - 1):
        a = landmarks[order[i]]
        b = landmarks[order[i + 1]]
        segment = nx.shortest_path(cost_graph, a, b, weight="cost")
        if full_path and full_path[-1] == segment[0]:
            full_path.extend(segment[1:])
        else:
            full_path.extend(segment)

    return "success", full_path
