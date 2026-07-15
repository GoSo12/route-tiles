import numpy as np

from statshunters import compute_zones


ADJOINING = [(1, 0), (-1, 0), (0, 1), (0, -1)]


def _parse_tiles(tiles):
    return set(tuple(int(v) for v in t.split('_')) for t in tiles)


def _tile_id(x, y):
    return "{}_{}".format(x, y)


def _build_zones(tile_set):
    """Group tiles into connected zones and, for each, build a grid + integral
    image plus its own local current max square size."""
    zones = []
    for zone in compute_zones(tile_set):
        xs = [t[0] for t in zone]
        ys = [t[1] for t in zone]
        x_min, x_max = min(xs) - 1, max(xs) + 1
        y_min, y_max = min(ys) - 1, max(ys) + 1
        w, h = x_max - x_min + 1, y_max - y_min + 1

        grid = np.zeros((w, h), dtype=np.int32)
        for (x, y) in zone:
            grid[x - x_min, y - y_min] = 1

        integral = np.zeros((w + 1, h + 1), dtype=np.int32)
        integral[1:, 1:] = grid.cumsum(axis=0).cumsum(axis=1)

        current_max = 0
        max_k = min(w, h)
        for k in range(1, max_k + 1):
            sums = (integral[k:, k:] - integral[:-k, k:]
                    - integral[k:, :-k] + integral[:-k, :-k])
            if not np.any(sums == k * k):
                break
            current_max = k

        zones.append({'grid': grid, 'integral': integral, 'x_min': x_min,
                      'y_min': y_min, 'w': w, 'h': h, 'current_max': current_max})
    return zones


def _is_connected(coords):
    """4-connectivity check: can every tile be reached from any other by
    stepping only through tiles in the same set?"""
    if not coords:
        return True
    coords = set(coords)
    start = next(iter(coords))
    seen = {start}
    stack = [start]
    while stack:
        x, y = stack.pop()
        for dx, dy in ADJOINING:
            n = (x + dx, y + dy)
            if n in coords and n not in seen:
                seen.add(n)
                stack.append(n)
    return seen == coords


def find_best_square_completion(tiles, max_extra=30, candidates_per_size=200):
    """Find the cheapest way to make the current *global* max square bigger:
    across every square size larger than the record and every zone, pick the
    window whose missing tiles are (a) as few as possible and (b) form a
    single *connected* patch - riding through several separate holes takes
    several separate detours, a single connected gap does not.

    A single-tile "did this one flip the record" check (the previous
    approach) is nearly always empty once the record gets large - jumping a
    size class by chance with one extra tile becomes rare. Since one ride
    typically adds 50-100 tiles at once, what is actually useful is the
    smallest connected patch of missing tiles worth specifically riding
    through, even if that number is well above 1.
    """
    tile_set = _parse_tiles(tiles)
    if not tile_set:
        return {'size': 0, 'gain': 0, 'missingCount': 0, 'tiles': []}

    zones = _build_zones(tile_set)
    global_max = max((z['current_max'] for z in zones), default=0)

    best = None  # (missing_count, size, tile_ids)
    for z in zones:
        grid, integral = z['grid'], z['integral']
        w, h, x_min, y_min = z['w'], z['h'], z['x_min'], z['y_min']
        max_k = min(w, h)
        for k in range(global_max + 1, min(global_max + max_extra, max_k) + 1):
            sums = (integral[k:, k:] - integral[:-k, k:]
                    - integral[k:, :-k] + integral[:-k, :-k])
            missing = k * k - sums

            if best is not None and int(missing.min()) >= best[0]:
                continue

            # Inspect windows in ascending order of missing-tile count and
            # stop at the first one whose gap is a single connected patch.
            flat_order = np.argsort(missing, axis=None)
            for idx in flat_order[:candidates_per_size]:
                count = int(missing.flat[idx])
                if best is not None and count >= best[0]:
                    break
                i, j = np.unravel_index(idx, missing.shape)
                sub = grid[i:i + k, j:j + k]
                coords = [(i + dx + x_min, j + dy + y_min)
                          for dx, dy in np.argwhere(sub == 0)]
                if _is_connected(coords):
                    best = (count, k, [_tile_id(x, y) for x, y in coords])
                    break

    if best is None:
        return {'size': global_max, 'gain': 0, 'missingCount': 0, 'tiles': []}

    missing_count, size, tile_ids = best
    return {'size': size, 'gain': size - global_max,
            'missingCount': missing_count, 'tiles': tile_ids}
