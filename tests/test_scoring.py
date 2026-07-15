from statshunters import compute_zones
from scoring import find_best_square_completion, _is_connected


def test_compute_zones_splits_disconnected_components():
    tiles = {(0, 0), (1, 0), (5, 5)}
    zones = compute_zones(tiles)
    zones_as_sets = sorted(zones, key=len)
    assert zones_as_sets == [{(5, 5)}, {(0, 0), (1, 0)}] or zones_as_sets == [{(5, 5)}, {(1, 0), (0, 0)}]
    assert len(zones) == 2


def test_compute_zones_merges_4_connected_tiles():
    tiles = {(0, 0), (1, 0), (1, 1), (0, 1)}
    zones = compute_zones(tiles)
    assert len(zones) == 1
    assert zones[0] == tiles


def test_find_best_square_completion_empty():
    result = find_best_square_completion([])
    assert result == {'size': 0, 'gain': 0, 'missingCount': 0, 'tiles': []}


def test_find_best_square_completion_one_missing_corner():
    # 3 of a 2x2 square already visited - the 4th tile is the cheapest way
    # to grow from a 1x1 record to a 2x2.
    tiles = ["0_0", "1_0", "0_1"]
    result = find_best_square_completion(tiles)
    assert result['size'] == 2
    assert result['gain'] == 1
    assert result['missingCount'] == 1
    assert result['tiles'] == ["1_1"]


def test_find_best_square_completion_always_returns_connected_gap():
    # find_best_square_completion() only ever accepts a candidate window if
    # its missing tiles form one connected patch (see its docstring) -
    # regardless of the specific grid, the tiles it returns must pass
    # _is_connected().
    visited = set()
    for x in range(5):
        for y in range(5):
            visited.add((x, y))
    visited.discard((2, 2))
    visited.discard((2, 3))
    tiles = ["{}_{}".format(x, y) for (x, y) in visited]

    result = find_best_square_completion(tiles)
    coords = [tuple(int(v) for v in t.split('_')) for t in result['tiles']]
    assert _is_connected(coords)


def test_is_connected():
    assert _is_connected([(0, 0), (1, 0), (1, 1)]) is True
    assert _is_connected([(0, 0), (5, 5)]) is False
    assert _is_connected([]) is True
