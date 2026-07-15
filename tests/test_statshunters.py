import json

import pytest

from statshunters import (
    _normalize_share_url,
    statshunters_path,
    tiles_from_activities,
    activity_filter_options,
    compute_max_square,
    compute_cluster,
)


# --- URL validation: regression tests for the SSRF / path-traversal fix ---
# (a previous version fell back to using the raw, unvalidated input when a
# loose host-agnostic regex didn't match, which let a crafted "url" query
# param make the server fetch arbitrary hosts and/or escape the intended
# on-disk cache directory - see UPDATES.md)

@pytest.mark.parametrize("url,expected", [
    ("https://statshunters.com/share/abcdef123456", "https://statshunters.com/share/abcdef123456"),
    ("https://statshunters.com/share/abcdef123456/", "https://statshunters.com/share/abcdef123456"),
    ("https://statshunters.com/share/abcdef123456/activities", "https://statshunters.com/share/abcdef123456"),
    ("https://statshunters.com/share/abcdef123456?foo=bar", "https://statshunters.com/share/abcdef123456"),
    ("HTTPS://STATSHUNTERS.COM/share/abcdef123456", "HTTPS://STATSHUNTERS.COM/share/abcdef123456"),
    ("  https://statshunters.com/share/abcdef123456  ", "https://statshunters.com/share/abcdef123456"),
    ("http://www.statshunters.com/share/abc123", "http://www.statshunters.com/share/abc123"),
])
def test_normalize_share_url_accepts_real_links(url, expected):
    assert _normalize_share_url(url) == expected


@pytest.mark.parametrize("url", [
    "..",
    "http://169.254.169.254/share/x",
    "http://evil.example.com/share/abcdef123456",
    "https://statshunters.com.evil.com/share/abcdef123456",
    "https://statshunters.com/share/../../../etc",
    "https://statshunters.com/notshare/abcdef123456",
    "ftp://statshunters.com/share/abcdef123456",
    "",
    "not a url at all",
])
def test_normalize_share_url_rejects_everything_else(url):
    with pytest.raises(ValueError):
        _normalize_share_url(url)


def test_statshunters_path_rejects_traversal(tmp_path):
    with pytest.raises(ValueError):
        statshunters_path("..", tmp_path)
    with pytest.raises(ValueError):
        statshunters_path("http://evil.com/share/x", tmp_path)


def test_statshunters_path_stays_inside_folder(tmp_path):
    path = statshunters_path("https://statshunters.com/share/abc123/", tmp_path)
    assert path.parent == tmp_path
    assert path.name == "abc123"
    assert path.exists()


# --- activity parsing / empty-input guards ---

def _write_activities(activities_dir, activities):
    activities_dir.mkdir(parents=True, exist_ok=True)
    (activities_dir / "activities_1.json").write_text(json.dumps({"activities": activities}))


def test_tiles_from_activities_basic(tmp_path):
    _write_activities(tmp_path, [
        {"type": "Ride", "tiles": [{"x": 1, "y": 2}, {"x": 1, "y": 3}]},
        {"type": "Run", "tiles": [{"x": 1, "y": 2}]},
    ])
    tiles = tiles_from_activities(tmp_path)
    assert tiles == frozenset({"1_2", "1_3"})


def test_tiles_from_activities_filtered_by_type(tmp_path):
    _write_activities(tmp_path, [
        {"type": "Ride", "tiles": [{"x": 1, "y": 2}]},
        {"type": "Run", "tiles": [{"x": 9, "y": 9}]},
    ])
    tiles = tiles_from_activities(tmp_path, activity_type="Run")
    assert tiles == frozenset({"9_9"})


def test_activity_filter_options(tmp_path):
    _write_activities(tmp_path, [
        {"type": "Ride", "tiles": []},
        {"type": "Run", "tiles": []},
        {"type": "Ride", "tiles": []},
    ])
    assert activity_filter_options(tmp_path) == {"types": ["Ride", "Run"]}


def test_compute_max_square_empty_tiles_does_not_crash():
    # Regression test: unary_union() on an empty polygon list used to raise
    # inside fastkml ("Illegal geometry type") before this guard existed.
    assert compute_max_square(frozenset()) == 0


def test_compute_cluster_empty_tiles_does_not_crash():
    assert compute_cluster(frozenset()) == 0


def test_compute_max_square_real_kml(tmp_path):
    _write_activities(tmp_path, [
        {"type": "Ride", "tiles": [{"x": x, "y": y} for x in range(3) for y in range(3)]},
    ])
    tiles = tiles_from_activities(tmp_path)
    result = compute_max_square(tiles)
    assert isinstance(result, str) and "<coordinates>" in result
