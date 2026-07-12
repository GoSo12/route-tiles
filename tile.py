import mercantile
from shapely.geometry import Point, LineString, LinearRing, Polygon
from fastkml import kml, styles

from utils import *

# Tile-hunting zoom level (~1km2 tiles) - matches Squadrats/Statshunters/
# VeloViewer's own grid, and every tile ID ("x_y") already stored/imported
# from those services.
ZOOM = 14


def coord_from_tile(x, y=None):
    """(lat, lon) of a tile's north-west corner."""
    if y is None:
        s = x.split('_')
        x = int(s[0])
        y = int(s[1])
    ul = mercantile.ul(x, y, ZOOM)
    return ul.lat, ul.lng


def geom_from_tile(x):
    """[[lon, lat] of NW corner, [lon, lat] of SE corner] for a tile ID."""
    s = x.split('_')
    x = int(s[0])
    y = int(s[1])
    b = mercantile.bounds(x, y, ZOOM)
    return [[b.west, b.north], [b.east, b.south]]


def tile_from_coord(lat, lon, output="list"):
    t = mercantile.tile(lon, lat, ZOOM)
    if output == "list":
        return t.x, t.y
    else:
        return "{}_{}".format(t.x, t.y)


class Coord(object):
    def __init__(self, lat, lon, node_id=None):
        self.lat = lat
        self.lon = lon
        self.nodeId = node_id

    @property
    def latlon(self):
        return self.lat, self.lon

    def __repr__(self):
        return "{},{}({})".format(self.lat, self.lon, self.nodeId)

    @property
    def edges(self):
        return [self.latlon]

    @property
    def entryNodeId(self):
        return [self]

    @property
    def entry_nodes_id(self):
        return [self.nodeId]


class CoordDict(object):
    def __init__(self, router):
        self.dict = {}
        self._router = router
        pass

    def get(self, lat, lon, node_id=None):
        name = "{}_{}".format(lat, lon)
        if name in self.dict:
            return self.dict[name]
        else:
            if node_id is None:
                node_id = self._router.find_node(lat, lon)
                # lat, lon = router.nodeLatLon(nodeId)
            coord = Coord(lat, lon, node_id)
            self.dict[name] = coord
            return coord


class ZoneWithEntries(object):
    def __init__(self, name=None):
        self.name = name
        self.entryNodeId = []
        self._entryNodesId = None

    @property
    def entry_nodes_id(self):
        if self._entryNodesId is None:
            self._entryNodesId = [n.nodeId for n in self.entryNodeId]
        return self._entryNodesId


class Tile(ZoneWithEntries):
    def __init__(self, uid, y=None):
        super().__init__(name='')
        if isinstance(uid, str):
            self.uid = uid
            s = uid.split("_")
            self.x = s[0]
            self.y = s[1]
        elif y is None:
            s = tile_from_coord((min([x[1] for x in uid]) + max([x[1] for x in uid])) / 2,
                                (max([x[0] for x in uid]) + min([x[0] for x in uid])) / 2)
            self.x = s[0]
            self.y = s[1]
            self.uid = "{0.x}_{0.y}".format(self)
        else:
            self.x = uid
            self.y = y
            self.uid = "{0.x}_{0.y}".format(self)

        geometry = geom_from_tile(self.uid)

        self.lonW = min([x[0] for x in geometry])
        self.lonE = max([x[0] for x in geometry])
        self.latS = min([x[1] for x in geometry])
        self.latN = max([x[1] for x in geometry])
        self.lon = (self.lonE + self.lonW) / 2
        self.lat = (self.latS + self.latN) / 2
        self.uid = "{0.x}_{0.y}".format(self)
        self.entryNodeId = []
        self.routesEntryNodes = {}
        self.polygon = Polygon([(self.lonW, self.latN), (self.lonW, self.latS), (self.lonE, self.latS),  (self.lonE, self.latN)])

    @property
    def middle(self):
        return self.lat, self.lon

    def __repr__(self):
        if self.name:
            return self.name
        return "Tile {}".format(self.name or self.uid)

    @property
    def edges(self):
        nw = (self.latN, self.lonW)
        ne = (self.latN, self.lonE)
        se = (self.latS, self.lonE)
        sw = (self.latS, self.lonW)
        return [nw, ne, se, sw]

    @property
    def segments(self):
        nw = (self.latN, self.lonW)
        ne = (self.latN, self.lonE)
        se = (self.latS, self.lonE)
        sw = (self.latS, self.lonW)
        return [(nw, ne), (ne, se), (se, sw), (sw, nw)]

    def linear_ring(self, offset=0):
        delta_lat = (self.latN - self.latS) / (1000 * distance((self.latN, self.lonW), (self.latS, self.lonW))) * offset
        delta_lon = (self.lonW - self.lonE) / (1000 * distance((self.latN, self.lonW), (self.latN, self.lonE))) * offset
        nw = (self.latN - delta_lat, self.lonW - delta_lon)
        ne = (self.latN - delta_lat, self.lonE + delta_lon)
        se = (self.latS + delta_lat, self.lonE + delta_lon)
        sw = (self.latS + delta_lat, self.lonW - delta_lon)
        return LinearRing([nw, ne, se, sw])

    @property
    def line_string_lon_lat(self):
        nw = (self.lonW, self.latN)
        ne = (self.lonE, self.latN)
        se = (self.lonE, self.latS)
        sw = (self.lonW, self.latS)
        return LineString([nw, ne, se, sw, nw])

    def to_dict(self):
        ne = (self.latN, self.lonE)
        sw = (self.latS, self.lonW)
        data = {'id': self.uid, 'bound': (sw, ne)}
        return data

    def get_entry_points(self, router):
        if self.entryNodeId:
            return
        router.get_area_rect(*self.edges[0], *self.edges[2])

        tile = self.linear_ring(offset=10)

        def add_entry_point(node):
            coord = Coord(*router.node_lat_lon(node), node)
            # if coord not in self.entryNodeId:
            if node not in [e.nodeId for e in self.entryNodeId]:
                self.entryNodeId.append(coord)

        new_points = []
        new_points_id = []

        for node_a, nodes in list(router.routing.items()):
            latlon = router.node_lat_lon(node_a)
            if distance(latlon, (self.lat, self.lon)) > 5:
                continue
            point_a = Point(*latlon)
            for node_b in list(nodes):
                point_b = Point(*router.node_lat_lon(node_b))
                line = LineString([point_a, point_b])
                if line.intersects(tile):
                    intersect_points = line.intersection(tile)
                    if intersect_points.geom_type == "Point":
                        intersect_points = [intersect_points]
                    elif intersect_points.geom_type == "LineString":
                        intersect_points = [Point(intersect_points.coords[0]), Point(intersect_points.coords[-1])]
                    else:
                        intersect_points = list(intersect_points.geoms)

                    intersect_points = list(intersect_points)

                    if point_a in intersect_points:
                        add_entry_point(node_a)
                        intersect_points.remove(point_a)
                    if point_b in intersect_points:
                        add_entry_point(node_b)
                        intersect_points.remove(point_b)

                    intersect_points.sort(key=lambda p: LineString([point_a, p]).length)

                    nodes_id = []
                    for point in intersect_points:
                        if point not in new_points:
                            node_id = int((str(self.uid) + str(len(new_points))).replace("_", ""))
                            router.rnodes[node_id] = (point.x, point.y)
                            new_points.append(point)
                            new_points_id.append(node_id)
                            add_entry_point(node_id)
                        else:
                            node_id = new_points_id[new_points.index(point)]
                        nodes_id.append(node_id)

                    for node_id in nodes_id:
                        if node_id not in router.routing:
                            router.routing[node_id] = {}

                    weight = router.routing[node_a][node_b]

                    # Splitting node_a->node_b into a chain through the new
                    # synthetic entry node(s) drops the original edge's
                    # curve shape/real length unless explicitly carried
                    # over - every tile crossing (at least 2 per visited
                    # tile) would otherwise draw and cost a straight line
                    # even where the real road curves.
                    edge_shapes = getattr(router, "edge_shapes", None)
                    edge_lengths = getattr(router, "edge_lengths", None)
                    if edge_shapes is not None or edge_lengths is not None:
                        original_shape = router.shape_between(node_a, node_b)
                        original_length = router.edge_length(node_a, node_b)
                        total_dist = distance((point_a.x, point_a.y), (point_b.x, point_b.y))

                        def frac_at(p):
                            if total_dist <= 0:
                                return 1.0
                            return distance((point_a.x, point_a.y), (p.x, p.y)) / total_dist

                        chain_nodes = [node_a] + nodes_id + [node_b]
                        chain_fracs = [0.0] + [frac_at(p) for p in intersect_points] + [1.0]
                        n_shape = len(original_shape)

                        for i in range(len(chain_nodes) - 1):
                            a_frac, b_frac = chain_fracs[i], chain_fracs[i + 1]
                            pair = (chain_nodes[i], chain_nodes[i + 1])
                            if edge_shapes is not None:
                                edge_shapes[pair] = original_shape[round(a_frac * n_shape):round(b_frac * n_shape)]
                            if edge_lengths is not None and original_length is not None:
                                edge_lengths[pair] = original_length * (b_frac - a_frac)

                    if node_a not in router.not_update_routing:
                        router.not_update_routing[node_a] = []
                    router.not_update_routing[node_a].append(node_b)
                    n0 = node_a
                    for n in nodes_id:
                        router.routing[n0][n] = weight
                        router.routing[n][node_b] = weight
                        router.routing[n0].pop(node_b)
                        n0 = n

        print("Tile {} has {} entry nodes".format(self.name or self.uid, len(self.entryNodeId)))
        return


def tiles_to_kml(tiles, filename, name):
    # Create the root KML object
    k = kml.KML()
    ns = '{http://www.opengis.net/kml/2.2}'

    s = styles.Style(id="s", styles=[styles.LineStyle(color="ff0000ff", width=1)])

    # Create a KML Document and add it to the KML root object
    d = kml.Document(ns, name=name, styles=[s])
    k.append(d)

    # Create a KML Folder and add it to the Document
    f = kml.Folder(ns, name=name)
    d.append(f)

    # Create a Placemark with a simple polygon geometry and add it to the
    # second folder of the Document
    for tile_id in tiles:
        tile = Tile(tile_id)
        p = kml.Placemark(ns, tile_id, styleUrl="#s")
        p.geometry = tile.line_string_lon_lat
        f.append(p)

    print(k.to_string(prettyprint=True))
    with open(filename, 'w') as hf:
        hf.write(k.to_string(prettyprint=True))
    return True