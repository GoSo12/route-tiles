from ortools_router import _cost_graph


class FakeDatastore:
    """Minimal stand-in for OsmnxDatastore, just enough surface for
    _cost_graph(): .rnodes, .routing, and an optional .edge_length()."""

    def __init__(self, rnodes, routing, edge_lengths=None):
        self.rnodes = rnodes
        self.routing = routing
        self._edge_lengths = edge_lengths or {}

    def edge_length(self, a, b):
        if (a, b) in self._edge_lengths:
            return self._edge_lengths[(a, b)]
        if (b, a) in self._edge_lengths:
            return self._edge_lengths[(b, a)]
        return None


def test_cost_graph_uses_real_edge_length_when_plausible():
    # Two nodes ~1km apart (roughly 0.009 degrees latitude), registered
    # edge_length matches reality - must be used as-is (not overridden).
    rnodes = {1: (48.0, 11.0), 2: (48.009, 11.0)}
    routing = {1: {2: 1.0}, 2: {1: 1.0}}
    ds = FakeDatastore(rnodes, routing, edge_lengths={(1, 2): 1.0})

    g = _cost_graph(ds)
    assert g[1][2]["cost"] == 1.0 / 1.0


def test_cost_graph_floors_bogus_short_edge_length():
    # Regression test for the "wilde Sprünge" root cause: a corrupted
    # edge_length (e.g. from a synthetic entry-node id collision) registers
    # a real ~1.6km hop as ~0.02km - _cost_graph() must not let the solver
    # treat that as a genuine shortcut; it should floor the cost at the
    # straight-line distance between the endpoints instead.
    rnodes = {1: (48.502137437417744, 11.174322263516858),
              2: (48.51651441670688, 11.178875536727503)}
    routing = {1: {2: 1.0}, 2: {1: 1.0}}
    ds = FakeDatastore(rnodes, routing, edge_lengths={(1, 2): 0.0213})  # bogus, real is ~1.63km

    g = _cost_graph(ds)
    straight_km = 1.63  # approx, verified below with a looser bound
    assert g[1][2]["cost"] > 1.0  # not the bogus ~0.02km-based cost
    assert abs(g[1][2]["cost"] - straight_km) < 0.1


def test_cost_graph_skips_zero_weight_edges():
    rnodes = {1: (48.0, 11.0), 2: (48.01, 11.0)}
    routing = {1: {2: 0}, 2: {1: 0}}
    ds = FakeDatastore(rnodes, routing)

    g = _cost_graph(ds)
    assert not g.has_edge(1, 2)


def test_cost_graph_falls_back_to_straight_line_without_edge_length():
    rnodes = {1: (48.0, 11.0), 2: (48.009, 11.0)}
    routing = {1: {2: 1.0}, 2: {1: 1.0}}
    ds = FakeDatastore(rnodes, routing)  # no edge_lengths at all

    g = _cost_graph(ds)
    assert g[1][2]["cost"] > 0
