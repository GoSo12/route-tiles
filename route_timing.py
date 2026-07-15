import json
from pathlib import Path

HISTORY_PATH = Path(__file__).parent / "route_timing_history.json"

# Keeps the history file from growing forever - a few hundred data points
# per solver is already more than enough for the interpolation below, and
# recent completions are more representative than very old ones anyway.
_MAX_HISTORY_ENTRIES = 500


def _load():
    if not HISTORY_PATH.exists():
        return []
    try:
        return json.loads(HISTORY_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def record_timing(solver, param_value, elapsed_s):
    """Record one completed search: solver is 'exact'/'ortools'/'orienteering',
    param_value is the tile count (exact/ortools) or budget in km
    (orienteering) that took elapsed_s seconds to solve. Only call this for
    a genuine successful completion - an aborted or failed search's timing
    isn't representative of how long a full solve actually takes."""
    history = _load()
    history.append({"solver": solver, "param": param_value, "elapsed_s": elapsed_s})
    history = history[-_MAX_HISTORY_ENTRIES:]
    HISTORY_PATH.write_text(json.dumps(history))


def estimate_time(solver, param_value):
    """Estimate how many seconds a search with this solver/param_value will
    take, by linearly interpolating between the two recorded data points
    (for the same solver) that bracket param_value, or extrapolating from
    the nearest edge if it falls outside the recorded range. Returns None
    if there's no history yet for this solver."""
    points = sorted(
        (h["param"], h["elapsed_s"]) for h in _load() if h["solver"] == solver
    )
    if not points:
        return None
    if len(points) == 1:
        return points[0][1]

    if param_value <= points[0][0]:
        # A smaller-than-ever-seen instance is unlikely to be slower than
        # the smallest one observed so far - flat extrapolation is safer
        # than a downward-sloping line turning negative.
        return points[0][1]

    if param_value >= points[-1][0]:
        (x0, y0), (x1, y1) = points[-2], points[-1]
        if x1 == x0:
            return y1
        slope = (y1 - y0) / (x1 - x0)
        return max(0.0, y1 + slope * (param_value - x1))

    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= param_value <= x1:
            if x1 == x0:
                return y0
            ratio = (param_value - x0) / (x1 - x0)
            return y0 + ratio * (y1 - y0)

    return points[-1][1]  # unreachable given the bounds checks above
