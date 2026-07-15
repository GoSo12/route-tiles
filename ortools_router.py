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
        u_latlon = datastore.rnodes.get(u)
        for v, weight in neighbors.items():
            if weight <= 0:
                continue
            real_dist = segment_distance(datastore, u, v)
            v_latlon = datastore.rnodes.get(v)
            if u_latlon and v_latlon:
                # No real road can be shorter than the straight line between
                # its endpoints (mod float/geometry slack) - flooring here
                # catches a corrupted edge_length regardless of how it got
                # corrupted, e.g. a synthetic entry-node id silently reused
                # for two different physical points (see
                # _tile_representative_node), before the solver can pick
                # such a hop as an unrealistically cheap "shortcut". This is
                # the concrete mechanism behind the straight-line "wilde
                # Sprünge" jumps: a real ~1.6km gap once registered at ~21m.
                straight_km = distance(u_latlon, v_latlon)
                if real_dist < straight_km * 0.9:
                    real_dist = straight_km
            cost = real_dist / weight
            if g.has_edge(u, v):
                g[u][v]["cost"] = min(g[u][v]["cost"], cost)
            else:
                g.add_edge(u, v, cost=cost)
    return g


def _tile_representative_node(tile):
    """One real, routable point for an already-processed tile.

    tile.get_entry_points() must already have been called by the caller,
    on this exact Tile instance, before this is invoked. It must NOT be
    (re-)called here: Tile.get_entry_points() only guards against running
    twice on the *same instance* (it early-returns once self.entryNodeId is
    set) - it does nothing to stop a second, independent Tile instance for
    the same tile-id from re-scanning router.routing and finding a
    *different* set of boundary crossings, because the first call has
    already spliced synthetic nodes into that same shared routing dict.
    The synthetic node-id scheme (tile uid + a counter local to that one
    call) then reuses the same ids for these different physical points,
    silently overwriting one location's edge_lengths/edge_shapes with
    another's. That is the exact, confirmed mechanism behind the "wilde
    Sprünge" bug (a real ~1.6km hop ending up registered at ~21m): this
    function used to build its own throwaway Tile and call
    get_entry_points() again, redundantly, after MyRouter._run() (or
    plan_orienteering_route) had already done it properly. Every caller
    must now compute entry points exactly once per tile per search and
    pass the resulting Tile in here.
    """
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


def solve_tile_route(datastore, start_node, end_node, tiles, waypoint_nodes=None, time_limit_s=30):
    """Find a route visiting one representative point per tile (plus any
    mandatory waypoint nodes), starting at start_node and ending at end_node.

    tiles: already-processed Tile objects (tile.get_entry_points(datastore)
    already called by the caller - see _tile_representative_node for why
    this function must not do that itself).

    Returns (status, node_path) in the same shape as
    tilesrouter.MyRouter.do_route_with_crossing_zone:
    ("success"/"no_route", [node_id, ...]).
    """
    landmarks = (
        [start_node, end_node]
        + list(waypoint_nodes or [])
        + [_tile_representative_node(t) for t in tiles]
    )
    n = len(landmarks)
    cost_graph = _cost_graph(datastore)

    # Every landmark is mandatory (no AddDisjunction below) - if even one of
    # them sits in a different connected component than start_node, the
    # tour is flat-out infeasible, not just expensive. Catching that here
    # and failing cleanly avoids two bad outcomes downstream: OR-Tools
    # still trying to use the UNREACHABLE_PENALTY_M fallback below (a
    # large but *finite* cost, so a large/otherwise-bad problem can still
    # pick it) and then crashing during path reconstruction ("No path
    # between ..."), or - if the unreachable landmark happens to sit in a
    # small pocket with a real but very long path back in - rendering as
    # a nonsensical straight-line "shortcut" instead of a real detour.
    # Found via a real reproduction: find_node() picking a start point
    # whose nearest graph node had zero routing edges for the current
    # mode (now fixed at the source in osmnx_datastore.find_node(), this
    # check stays as defense in depth for any other way a landmark could
    # end up disconnected, e.g. a tile only reachable via a genuinely
    # isolated road fragment).
    if start_node not in cost_graph:
        return "no_route", []
    reachable = nx.node_connected_component(cost_graph, start_node)
    if any(lm not in reachable for lm in landmarks):
        return "no_route", []

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
