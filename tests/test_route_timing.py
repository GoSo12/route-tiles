import route_timing


def test_estimate_time_no_history_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(route_timing, "HISTORY_PATH", tmp_path / "history.json")
    assert route_timing.estimate_time("ortools", 20) is None


def test_estimate_time_single_point_returns_that_value(tmp_path, monkeypatch):
    monkeypatch.setattr(route_timing, "HISTORY_PATH", tmp_path / "history.json")
    route_timing.record_timing("ortools", 20, 15.0)
    assert route_timing.estimate_time("ortools", 5) == 15.0
    assert route_timing.estimate_time("ortools", 50) == 15.0


def test_estimate_time_interpolates_between_two_points(tmp_path, monkeypatch):
    monkeypatch.setattr(route_timing, "HISTORY_PATH", tmp_path / "history.json")
    route_timing.record_timing("ortools", 20, 10.0)
    route_timing.record_timing("ortools", 40, 30.0)
    assert route_timing.estimate_time("ortools", 30) == 20.0
    assert route_timing.estimate_time("ortools", 20) == 10.0
    assert route_timing.estimate_time("ortools", 40) == 30.0


def test_estimate_time_extrapolates_below_range_flat(tmp_path, monkeypatch):
    monkeypatch.setattr(route_timing, "HISTORY_PATH", tmp_path / "history.json")
    route_timing.record_timing("ortools", 20, 10.0)
    route_timing.record_timing("ortools", 40, 30.0)
    # below the smallest known value -> flat extrapolation (never negative,
    # never a downward-sloping guess)
    assert route_timing.estimate_time("ortools", 5) == 10.0


def test_estimate_time_extrapolates_above_range_never_negative(tmp_path, monkeypatch):
    monkeypatch.setattr(route_timing, "HISTORY_PATH", tmp_path / "history.json")
    route_timing.record_timing("ortools", 20, 30.0)
    route_timing.record_timing("ortools", 40, 10.0)  # decreasing slope on purpose
    # linear extrapolation with a negative slope must be floored at 0, not
    # go negative for a large enough param_value
    estimate = route_timing.estimate_time("ortools", 1000)
    assert estimate >= 0.0


def test_estimate_time_keeps_solvers_independent(tmp_path, monkeypatch):
    monkeypatch.setattr(route_timing, "HISTORY_PATH", tmp_path / "history.json")
    route_timing.record_timing("ortools", 20, 10.0)
    route_timing.record_timing("orienteering", 20, 999.0)
    assert route_timing.estimate_time("ortools", 20) == 10.0


def test_history_capped_at_max_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(route_timing, "HISTORY_PATH", tmp_path / "history.json")
    monkeypatch.setattr(route_timing, "_MAX_HISTORY_ENTRIES", 5)
    for i in range(10):
        route_timing.record_timing("ortools", i, float(i))
    history = route_timing._load()
    assert len(history) == 5
    # only the most recent entries survive
    assert [h["param"] for h in history] == [5, 6, 7, 8, 9]
