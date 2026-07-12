"""Post-processing step for a computed route: remove redundant out-and-back
detours ("dead ends") made only to touch a tile the route already crosses
somewhere else anyway.

The routing solvers (both the exact search and the OR-Tools one) pick a
single entry point per tile and route to it - if the chosen path happens to
also pass near/through that same tile again later for an unrelated reason,
the earlier special trip to touch it becomes pure waste: ride in, ride back
out the same way, for nothing the route wasn't already going to give you.
This module finds and removes that waste without ever dropping required
tile or waypoint coverage.
"""
from tile import tile_from_coord


def _node_tile(datastore, node, target_tile_ids):
    lat, lon = datastore.node_lat_lon(node)
    tid = tile_from_coord(lat, lon, output="str")
    return tid if tid in target_tile_ids else None


def remove_redundant_spurs(datastore, path, target_tile_ids, protected_nodes=None):
    """Remove any out-and-back loop (path revisits the same node) whose
    detour serves no purpose that isn't already covered by the rest of the
    route: every target tile touched inside the loop is also touched
    outside it, and no protected node (waypoints, the route's own start/end)
    is stranded inside it.

    Runs to a fixed point: after removing a loop, indices shift, so the scan
    restarts. Safe to call on an already-clean route (no-op).
    """
    target_tile_ids = set(target_tile_ids)
    protected = set(protected_nodes or ())

    path = list(path)
    if len(path) < 3:
        return path

    changed = True
    while changed:
        changed = False
        n = len(path)
        last_seen = {}
        # Never let the final node participate as the "closing" end of a
        # loop - for a loop route (start == end) that would collapse the
        # entire route down to just its start point.
        for i in range(n - 1):
            node = path[i]
            if node in last_seen:
                j = last_seen[node]
                segment = path[j + 1:i]

                if any(s in protected for s in segment):
                    last_seen[node] = i
                    continue

                loop_tiles = {_node_tile(datastore, s, target_tile_ids) for s in segment}
                loop_tiles.discard(None)

                if loop_tiles:
                    remaining = path[:j + 1] + path[i:]
                    remaining_tiles = {_node_tile(datastore, s, target_tile_ids) for s in remaining}
                    remaining_tiles.discard(None)
                    if not loop_tiles.issubset(remaining_tiles):
                        last_seen[node] = i
                        continue

                path = path[:j + 1] + path[i + 1:]
                changed = True
                break

            last_seen[node] = i

    return path
