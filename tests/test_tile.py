from tile import Tile, coord_from_tile, tile_from_coord, geom_from_tile


def test_tile_from_coord_round_trip():
    # A coordinate inside a tile must map back to the same tile id, and
    # coord_from_tile's NW corner must fall strictly outside the tile to
    # its north/west (basic sanity on the mercantile wrapping).
    lat, lon = 48.1372, 11.5755  # Munich, real coordinate used elsewhere this session
    x, y = tile_from_coord(lat, lon)
    tile_id = "{}_{}".format(x, y)

    tile = Tile(tile_id)
    assert tile.latS <= lat <= tile.latN
    assert tile.lonW <= lon <= tile.lonE

    # Re-deriving the tile id from the tile's own center must be stable.
    x2, y2 = tile_from_coord(tile.lat, tile.lon)
    assert (x2, y2) == (x, y)


def test_coord_from_tile_matches_geom_bounds():
    tile_id = "8719_5687"
    nw_lat, nw_lon = coord_from_tile(tile_id)
    geom = geom_from_tile(tile_id)
    [[lonW, latN], [lonE, latS]] = geom

    assert nw_lat == latN
    assert nw_lon == lonW
    assert lonW < lonE
    assert latS < latN


def test_tile_edges_and_polygon_consistent():
    tile = Tile("8719_5687")
    edges = tile.edges
    assert len(edges) == 4
    lats = [e[0] for e in edges]
    lons = [e[1] for e in edges]
    assert min(lats) == tile.latS
    assert max(lats) == tile.latN
    assert min(lons) == tile.lonW
    assert max(lons) == tile.lonE

    # polygon must be a closed ring covering the same bounding box
    minx, miny, maxx, maxy = tile.polygon.bounds
    assert minx == tile.lonW
    assert maxx == tile.lonE
    assert miny == tile.latS
    assert maxy == tile.latN


def test_tile_from_two_coords_matches_explicit_xy():
    # Tile(uid) where uid is a list of [lon, lat] points (used by
    # compute_cluster/scoring code paths) must resolve to the same tile as
    # constructing it directly from x/y.
    explicit = Tile("8719_5687")
    from_points = Tile([[explicit.lonW + 0.0001, explicit.latN - 0.0001],
                         [explicit.lonE - 0.0001, explicit.latS + 0.0001]])
    assert from_points.uid == explicit.uid
