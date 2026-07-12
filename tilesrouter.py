#!/usr/bin/python
# -*- coding: utf-8 -*-

import threading
from pathlib import Path

import gpxpy
import gpxpy.gpx
from shapely.geometry import Point, Polygon

from osmnx_datastore import OsmnxDatastore
from tile import Tile, CoordDict
from utils import *

def latlons_to_gpx(latlons, filename, name):
    gpx = gpxpy.gpx.GPX()

    # Create first track in our GPX:
    gpx_track = gpxpy.gpx.GPXTrack(name=name)
    gpx.tracks.append(gpx_track)

    # Create first segment in our GPX track:
    gpx_segment = gpxpy.gpx.GPXTrackSegment()
    gpx_track.segments.append(gpx_segment)

    # Create points:
    for coord in latlons:
        gpx_segment.points.append(gpxpy.gpx.GPXTrackPoint(coord[0], coord[1]))

    with open(filename, 'w', encoding="utf8") as hf:
        hf.write(gpx.to_xml())
    return True


class Route(object):
    def __init__(self, route, router):
        self.route = route
        self.routeLatLons = self._build_latlons(route, router)
        self.length = self.compute_length(self.routeLatLons)

    @staticmethod
    def _build_latlons(route, router):
        """Insert the real road curve between consecutive nodes, where one
        is known (osmnx's graph simplification merges shape points into a
        single edge but keeps its geometry as an attribute) - otherwise the
        route would cut straight across every bend between intersections."""
        shape_between = getattr(router, "shape_between", None)
        latlons = []
        for i, node in enumerate(route):
            latlons.append(router.node_lat_lon(node))
            if shape_between and i < len(route) - 1:
                latlons.extend(shape_between(node, route[i + 1]))
        return latlons

    @staticmethod
    def compute_length(route_latlons):
        length = 0
        previous = route_latlons[0]
        for latlon in route_latlons[1:]:
            length += distance(previous, latlon)
            previous = latlon
        return length

    def to_gpx(self, filename, name):
        return latlons_to_gpx(self.routeLatLons, filename, name)


def segment_distance(router, a, b):
    """Real road distance (km) between two directly-connected nodes a->b.
    Falls back to straight-line distance for edges with no known curve
    (synthetic tile-entry nodes, waypoints) - straight-line distance
    underestimates curvy roads, which is why real edge length is preferred
    whenever the router can provide it."""
    edge_length = getattr(router, "edge_length", None)
    if edge_length:
        length = edge_length(a, b)
        if length is not None:
            return length
    return distance(router.rnodes[a], router.rnodes[b])


def debug_export_tiles(tiles):
    with open('debug/tiles.js', 'w') as hf:
        hf.write("var tiles = [\n")
        for t in tiles:
            hf.write(" [ \n")
            for lat, lon in t.edges:
                hf.write("[{},{}],\n".format(lat, lon))
            hf.write("  ],\n")
        hf.write("];\n")
        hf.write("var nodes = [\n")
        for t in tiles:
            for e in t.entryNodeId:
                hf.write("[{},{}],\n".format(*e.latlon))
        hf.write("];\n")

ERR_NO = 0
ERR_NO_TILE_ENTRY_POINT = 1
ERR_ABORT_REQUEST = 2
ERR_ROUTE_ERROR = 1000
ERR_UNEXPECTED = 1001

# Above this many tiles, do_route_with_crossing_zone's exact combinatorial
# search (2^N states) becomes impractically slow - switch to the OR-Tools
# based approximate solver instead, which scales to ~100 tiles in bounded
# time at the cost of only considering one representative point per tile.
OR_TOOLS_TILE_THRESHOLD = 15

class MyRouter(object):
    def __init__(self, router, start, end, tiles_ids, ways_points, config, gravel_tiles=None):
        self.router = router
        self._min_route = None
        self.min_length = None
        self.error_code = ERR_NO
        self.error_args = ""
        self._exit = False
        self._complete = False
        self.start = start
        self.end = end
        self.waypoints = ways_points
        self.tiles_ids = tiles_ids
        self.progress = 100.0
        self.config = config
        self.stored_tiles = {}
        # Tiles the user has explicitly opted to allow gravel/unpaved
        # surfaces for, after a first attempt found no paved entry point.
        self.gravel_tiles = set(gravel_tiles or [])

    def abort(self):
        self._exit = True

    @property
    def is_complete(self):
        return self._complete

    def run(self):
        """Thread entry point: any unhandled exception here would otherwise
        kill the background thread silently, leaving is_complete False
        forever - the GUI would then show "searching" indefinitely with no
        error message at all."""
        try:
            return self._run()
        except Exception as e:
            print("Unexpected error during routing:", e)
            self.error_code = ERR_UNEXPECTED
            self.error_args = []
            self.progress = 100.0
            self._complete = True
            return False

    def _run(self):
        self.min_length = None
        self._min_route = None
        self.error_code = ERR_NO
        self.error_args = ""

        selected_tiles = []
        for t in self.tiles_ids:
            if self._exit:
                self.error_code = ERR_ABORT_REQUEST
                return False

            if t not in self.stored_tiles:
                self.stored_tiles[t] = Tile(t)
            tile = self.stored_tiles[t]
            if Polygon(tile.linear_ring()).contains(Point(self.start.latlon)) or \
                    Polygon(tile.linear_ring()).contains(Point(self.end.latlon)):
                print("tile is in start or end")
                continue
            if t in self.gravel_tiles and hasattr(self.router, "allow_gravel_near"):
                # Grow the radius only as far as actually needed. A large
                # blanket radius (needed for genuinely remote/sparse areas)
                # unlocks a dense tangle of extra track/path edges in a
                # well-connected area, which the routing solver then exploits
                # as an unrealistic "shortcut hub" - producing exactly the
                # zigzagging, unrealistic routes this was meant to prevent.
                for radius_km in (0.3, 0.6, 1.0, 1.5, 3.0):
                    self.router.allow_gravel_near(tile.lat, tile.lon, radius_km=radius_km)
                    tile.get_entry_points(self.router)
                    if tile.entryNodeId:
                        break
            else:
                tile.get_entry_points(self.router)
            selected_tiles.append(tile)
            if not self.stored_tiles[t].entryNodeId:
                self.error_code = ERR_NO_TILE_ENTRY_POINT
                self.error_args = [t]
                self._complete = True
                return False

        for wp in self.waypoints:
            selected_tiles.append(wp)

        debug_export_tiles(selected_tiles)

        tile_ids_used = [t.uid for t in selected_tiles if isinstance(t, Tile)]
        if len(tile_ids_used) > OR_TOOLS_TILE_THRESHOLD:
            # Local import: avoids a circular import (ortools_router imports
            # segment_distance from this module).
            from ortools_router import solve_tile_route
            self.progress = 50.0
            waypoint_nodes = [wp.nodeId for wp in self.waypoints]
            time_limit_s = min(90, max(15, len(tile_ids_used)))
            status, r = solve_tile_route(self.router, self.start.nodeId, self.end.nodeId,
                                          tile_ids_used, waypoint_nodes=waypoint_nodes,
                                          time_limit_s=time_limit_s)
        else:
            status, r = self.do_route_with_crossing_zone(self.start.nodeId, self.end.nodeId,
                                                         frozenset(selected_tiles),
                                                         self.config)
        if self._exit:
            # solve_tile_route()/do_route_with_crossing_zone() are blocking
            # calls with no internal abort check, so this is the earliest
            # point after a mid-solve abort request where we can honor it -
            # without this, an aborted OR-Tools solve would still complete
            # and be reported as a successful route.
            self.error_code = ERR_ABORT_REQUEST
            return False
        if status != "success":
            self.error_code = ERR_ROUTE_ERROR
            self.error_args = ""
            route = None
        else:
            from route_cleanup import remove_redundant_spurs
            protected_nodes = {self.start.nodeId, self.end.nodeId}
            protected_nodes.update(wp.nodeId for wp in self.waypoints)
            r = remove_redundant_spurs(self.router, r, tile_ids_used, protected_nodes)

            route = Route(r, router=self.router)
            print("length:", route.length)

            self.min_length = route.length
            self._min_route = route
            print("\n**** FIND MIN ROUTE {:.2f}km ****\n".format(self.min_length))

        self.progress = 100.0
        print_progress_bar(100, 100)
        self._complete = True
        return route

    @property
    def min_route(self):
        if self._min_route is None:
            return None
        if isinstance(self._min_route, str):
            self._min_route = Route([int(i) for i in self._min_route.split(",")], router=self.router)
        return self._min_route

    def explore_routes_tile_exit(self, start, tile, mandatoryNodes):
        """Do the routing"""
        _closed = set()
        _queue = []
        _closeNode = True

        if start in tile.routesEntryNodes:
            return tile.routesEntryNodes[start]

        tile_bounds = Polygon(tile.linear_ring(offset=9.9))

        find_routes = []

        def _export_queue(new_item=None):
            nonlocal _closed, _queue, _closeNode
            with open('debug/routes.js', 'w') as hf:
                hf.write("var routes = [\n")
                if new_item:
                    route = [int(i) for i in new_item["nodes"].split(",")]
                    hf.write(" { \n")
                    hf.write("  'name':'{0:.3f}',\n".format(new_item['cost']))
                    hf.write("  'length':{},\n".format(new_item['cost']))
                    hf.write("  'route':[\n")
                    for lat, lon in list(map(self.router.node_lat_lon, route)):
                        hf.write("[{},{}],\n".format(lat, lon))
                    hf.write("  ],\n")
                    hf.write("  },\n")
                for q in _queue+find_routes:
                    route = [int(i) for i in q["nodes"].split(",")]
                    hf.write(" { \n")
                    hf.write("  'name':'{0:.3f}',\n".format(q['cost']))
                    hf.write("  'length':{},\n".format(q['cost']))
                    hf.write("  'route':[\n")
                    for lat, lon in list(map(self.router.node_lat_lon, route)):
                        hf.write("[{},{}],\n".format(lat, lon))
                    hf.write("  ],\n")
                    hf.write("  },\n")
                hf.write("];\n")

        def _queue_insert(queue_item):
            nonlocal _queue
            # Try to insert, keeping the queue ordered by decreasing heuristic cost
            position = 0
            for test in _queue:
                if test["cost"] > queue_item["cost"]:
                    _queue.insert(position, queue_item)
                    break
                position += 1

            else:
                _queue.append(queue_item)

        # Define function that addes to the queue
        def _add_to_queue(item_start, item_end, queue_so_far, item_weight=1):
            """Add another potential route to the queue"""
            nonlocal _closed, _queue, _closeNode

            # Assume start and end nodes have positions
            if item_end not in self.router.rnodes or item_start not in self.router.rnodes:
                return

            # Get data around end node
            self.router.get_area(self.router.rnodes[item_end][0], self.router.rnodes[item_end][1])

            # Ignore if route is not traversible
            if item_weight == 0:
                return

            # Do not turn around at a node (don't do this: a-b-a)
            # if len(queueSoFar["nodes"].split(",")) >= 2 and queueSoFar["nodes"].split(",")[-2] == str(end):
            #    return

            edge_cost = segment_distance(self.router, item_start, item_end) / item_weight

            total_cost = queue_so_far["cost"] + edge_cost

            all_nodes = queue_so_far["nodes"] + "," + str(item_end)

            # Check if path queueSoFar+end is not forbidden
            for i in self.router.forbiddenMoves:
                if i in all_nodes:
                    _closeNode = False
                    return

            # Check if we have a way to 'end' node
            end_queue_item = None
            for i in _queue:
                if i["end"] == item_end:
                    end_queue_item = i
                    break

            if end_queue_item :
                # If we do, and known total_cost to end is lower we can ignore the queueSoFar path
                if end_queue_item["cost"] < total_cost:
                    return
                # If the queued way to end has higher total cost, remove it
                # (and add the queueSoFar scenario, as it's cheaper)
                elif end_queue_item:
                    _queue.remove(end_queue_item)

            # Check against mandatory turns
            force_next_nodes = None
            if queue_so_far.get("mandatoryNodes", None):
                force_next_nodes = queue_so_far["mandatoryNodes"]

            else:
                for activationNodes, nextNodes in self.router.mandatoryMoves.items():
                    if all_nodes.endswith(activationNodes):
                        _closeNode = False
                        force_next_nodes = nextNodes.copy()
                        break

            # Create a hash for all the route's attributes
            queue_item = {
                "cost": total_cost,
                "nodes": all_nodes,
                "end": item_end,
                "mandatoryNodes": force_next_nodes
            }
            _queue_insert(queue_item)

        queue_item = {
            "cost": 0,
            "nodes": str(start),
            "end": start,
            "mandatoryNodes": mandatoryNodes
        }
        _queue_insert(queue_item)

        while _queue:
            _closeNode = True
            # _export_queue()

            # Pop first item from queue for routing. If queue it's empty - it means no route exists
            next_item = _queue.pop(0)

            considered_node = next_item["end"]

            # If we already visited the node, ignore it
            if considered_node in _closed:
                continue

            # exit the zone - success
            if not tile_bounds.contains(Point(*self.router.node_lat_lon(considered_node))):
                find_routes.append(next_item)
                continue

            # Check if we preform a mandatory turn
            if next_item["mandatoryNodes"]:
                _closeNode = False
                next_node = next_item["mandatoryNodes"].pop(0)
                if considered_node in self.router.routing and \
                        next_node in self.router.routing.get(considered_node, {}).keys():
                    _add_to_queue(considered_node, next_node, next_item,
                                  self.router.routing[considered_node][next_node])

            # If no, add all possible nodes from x to queue
            elif considered_node in self.router.routing:
                for next_node, weight in list(self.router.routing[considered_node].items()):
                    if next_node not in _closed:
                        _add_to_queue(considered_node, next_node, next_item, weight)

            if _closeNode:
                _closed.add(considered_node)

        #_export_queue()
        tile.routesEntryNodes[start] = find_routes
        return find_routes

    def do_route_with_crossing_zone(self, start, end, zones, config):
        """Do the routing"""
        _closed = {(start, frozenset(zones))}
        _queue = []
        _closeNode = True
        _end = end
        min_dists = {}
        min_dists_fast = {}

        def _export_queue(new_item=None):
            nonlocal _closed, _queue, _closeNode
            with open('debug/routes.js', 'w') as hf:
                hf.write("var routes = [\n")
                if new_item:
                    route = [int(i) for i in new_item["nodes"].split(",")]
                    hf.write(" { \n")
                    hf.write("  'name':'{0}-{1:.3f}',\n".format(len(new_item['not_visited_zones']),
                                                                new_item['heuristic_cost']))
                    hf.write("  'length':{},\n".format(new_item['cost']))
                    hf.write("  'route':[\n")
                    for lat, lon in list(map(self.router.node_lat_lon, route)):
                        hf.write("[{},{}],\n".format(lat, lon))
                    hf.write("  ],\n")
                    hf.write("  },\n")
                for q in _queue:
                    route = [int(i) for i in q["nodes"].split(",")]
                    hf.write(" { \n")
                    hf.write("  'name':'{0}-{1:.3f}',\n".format(len(q['not_visited_zones']), q['heuristic_cost']))
                    hf.write("  'length':{},\n".format(q['cost']))
                    hf.write("  'route':[\n")
                    for lat, lon in list(map(self.router.node_lat_lon, route)):
                        hf.write("[{},{}],\n".format(lat, lon))
                    hf.write("  ],\n")
                    hf.write("  },\n")
                hf.write("];\n")

        def _queue_insert(queue_item):
            nonlocal _queue
            # Try to insert, keeping the queue ordered by decreasing heuristic cost
            position = 0
            for test in _queue:
                if test["heuristic_cost"] > queue_item["heuristic_cost"]:
                    _queue.insert(position, queue_item)
                    break
                position += 1

            else:
                _queue.append(queue_item)

        # Define function that addes to the queue
        def _add_to_queue(item_start, item_not_visited_zones, item_end, queue_so_far, item_weight=1):
            """Add another potential route to the queue"""
            nonlocal _closed, _queue, _closeNode, min_dists, min_dists_fast

            # Assume start and end nodes have positions
            if item_end not in self.router.rnodes or item_start not in self.router.rnodes:
                return

            # Get data around end node
            self.router.get_area(self.router.rnodes[item_end][0], self.router.rnodes[item_end][1])

            # Ignore if route is not traversible
            if item_weight == 0:
                return

            # Do not turn around at a node (don't do this: a-b-a)
            # if len(queueSoFar["nodes"].split(",")) >= 2 and queueSoFar["nodes"].split(",")[-2] == str(end):
            #    return

            edge_cost = segment_distance(self.router, item_start, item_end) / item_weight

            # if turn around add additional cost
            if config.get('turnaround_cost', 0)>0:
                queue_so_far_nodes = queue_so_far["nodes"].split(',')
                if len(queue_so_far_nodes)>2:
                    if str(item_end) == queue_so_far_nodes[-2]:
                        #_export_queue(queue_so_far)
                        #print("Turnaround cost")
                        edge_cost += config['turnaround_cost']

            total_cost = queue_so_far["cost"] + edge_cost

            def _min_dist(start_loc, tiles, end_loc, store=True, fast=False):
                nonlocal min_dists, min_dists_fast
                if self._exit:
                    return 0
                md = min_dists_fast if fast else min_dists
                # compute flyby min distance by visiting all tiles
                if len(tiles) == 0:
                    return distance(start_loc, end_loc)

                if (start_loc, frozenset(tiles), end_loc) in md:
                    return md[(start_loc, frozenset(tiles), end_loc)]

                min_dist = None
                for t in tiles:
                    remain_tiles = set(tiles) - {t}
                    if fast and len(t.entryNodeId) > 4:
                        ep = t.edges
                    else:
                        ep = [n.latlon for n in t.entryNodeId]
                    for entry in ep:
                        pa = distance(start_loc, entry)
                        pb = _min_dist(entry, remain_tiles, end_loc, fast=fast)
                        if min_dist is None or pa + pb < min_dist:
                            min_dist = pa + pb
                if store:
                    md[(start_loc, frozenset(tiles), end_loc)] = min_dist
                return min_dist

            # t = time.time() if len(min_dists)==0 else None
            hc = _min_dist(self.router.rnodes[item_end], item_not_visited_zones, self.router.rnodes[_end], False,
                           len(item_not_visited_zones) > 5)
            # if t:
            # print("min dist time:{}".format(time.time()-t))
            heuristic_cost = total_cost + hc

            all_nodes = queue_so_far["nodes"] + "," + str(item_end)

            # Check if path queueSoFar+end is not forbidden
            for i in self.router.forbiddenMoves:
                if i in all_nodes:
                    _closeNode = False
                    return

            # Check if we have a way to 'end' node
            end_queue_item = None
            for i in _queue:
                if (i["end"], i["not_visited_zones"]) == (item_end, item_not_visited_zones):
                    end_queue_item = i
                    break

            if end_queue_item :
                # If we do, and known total_cost to end is lower we can ignore the queueSoFar path
                if end_queue_item["cost"] < total_cost:
                    return
                # If the queued way to end has higher total cost, remove it
                # (and add the queueSoFar scenario, as it's cheaper)
                elif end_queue_item:
                    _queue.remove(end_queue_item)

            # Check against mandatory turns
            force_next_nodes = None
            if queue_so_far.get("mandatoryNodes", None):
                force_next_nodes = queue_so_far["mandatoryNodes"]

            else:
                for activationNodes, nextNodes in self.router.mandatoryMoves.items():
                    if all_nodes.endswith(activationNodes):
                        _closeNode = False
                        force_next_nodes = nextNodes.copy()
                        break

            # Create a hash for all the route's attributes
            queue_item = {
                "cost": total_cost,
                "heuristic_cost": heuristic_cost,
                "nodes": all_nodes,
                "end": item_end,
                "not_visited_zones": item_not_visited_zones,
                "mandatoryNodes": force_next_nodes
            }

            _queue_insert(queue_item)


        # Start by queueing all outbound links from the start node
        if start not in self.router.routing:
            raise KeyError("node {} doesn't exist in the graph".format(start))

        elif start == end and not zones:
            return "no_route", []

        else:
            not_visited_zones = frozenset(zones)
            for linkedNode in list(self.router.routing[start]):
                weight = self.router.routing[start][linkedNode]
                _add_to_queue(start, not_visited_zones, linkedNode, {"cost": 0, "nodes": str(start)}, weight)

        # Limit for how long it will search
        count = 0
        while not self._exit:
            count += 1
            _closeNode = True
            #_export_queue()

            # Pop first item from queue for routing. If queue it's empty - it means no route exists
            if len(_queue) > 0:
                next_item = _queue.pop(0)
            else:
                return "no_route", []

            considered_node = next_item["end"]
            not_visited_zones = next_item["not_visited_zones"]

            if not self.min_length or next_item['cost'] > self.min_length:
                self.min_length = next_item['cost']
                self._min_route = next_item['nodes']
                self.progress = 100.0 * next_item['cost'] / next_item['heuristic_cost']
                print_progress_bar(next_item['cost'], next_item['heuristic_cost'])

            is_enter_new_tile = False
            for zone in not_visited_zones:
                if considered_node in zone.entry_nodes_id:
                    # Enter in a new zone
                    not_visited_zones = not_visited_zones - {zone}
                    if config.get('turnaround_cost', 0)>0 and len(zone.entry_nodes_id)>1:
                        is_enter_new_tile = True
                        routes_across_tile = self.explore_routes_tile_exit(considered_node, zone, next_item['mandatoryNodes'])
                        for route in routes_across_tile:
                            first_nodes = next_item['nodes'].split(',')[:-1]
                            add_cost = 0
                            if first_nodes[-1] in route['nodes'].split(','):
                                add_cost += config.get('turnaround_cost', 0)


                            queue_item = {
                                "cost": next_item['cost'] + route['cost'] + add_cost,
                                "heuristic_cost": next_item['heuristic_cost'] + route['cost'] + add_cost,
                                "nodes": next_item['nodes'] + ',' + route['nodes'],
                                "end": route['end'],
                                "not_visited_zones": not_visited_zones,
                                "mandatoryNodes": route['mandatoryNodes']
                            }
                            _queue_insert(queue_item)
                            _closed.add((int(route['nodes'].split(',')[-2]), not_visited_zones))
            if is_enter_new_tile:
                _closed.add((considered_node, not_visited_zones))
                #_export_queue()
                continue

            # If we already visited the node, ignore it
            if (considered_node, not_visited_zones) in _closed:
                continue

            # Found the end node - success
            if considered_node == end:
                if len(not_visited_zones) == 0:
                    _export_queue(next_item)
                    print(next_item)
                    return "success", [int(i) for i in next_item["nodes"].split(",")]

            # Check if we preform a mandatory turn
            if next_item["mandatoryNodes"]:
                _closeNode = False
                next_node = next_item["mandatoryNodes"].pop(0)
                if considered_node in self.router.routing and \
                        next_node in self.router.routing.get(considered_node, {}).keys():
                    _add_to_queue(considered_node, not_visited_zones, next_node, next_item,
                                  self.router.routing[considered_node][next_node])

            # If no, add all possible nodes from x to queue
            elif considered_node in self.router.routing:
                for next_node, weight in list(self.router.routing[considered_node].items()):
                    if (next_node, not_visited_zones) not in _closed:
                        _add_to_queue(considered_node, not_visited_zones, next_node, next_item, weight)

            if _closeNode:
                _closed.add((considered_node, not_visited_zones))

        else:
            return "gave_up", []

    def generate_gpx(self, file_name, gpx_name):
        if self.min_route:
            return self.min_route.to_gpx(file_name, gpx_name)
        else:
            return False


class OrienteeringRunner(object):
    """Distance-budgeted planning ("start here, ~N km, which tiles are worth
    it?"), run in a background thread. Deliberately duck-types MyRouter's
    interface (progress/is_complete/error_code/error_args/min_route/abort)
    so RouteServer and the existing /route_status polling endpoint can
    handle it without any changes - only start_orienteering() below needs to
    know this class exists."""

    def __init__(self, router, start_loc, visited_tiles, budget_km):
        self.router = router
        self.start_loc = start_loc
        self.visited_tiles = visited_tiles
        self.budget_km = budget_km
        self.error_code = ERR_NO
        self.error_args = ""
        self._exit = False
        self._complete = False
        self.progress = 50.0
        self._min_route = None
        self.selected_tiles = []

    def abort(self):
        self._exit = True

    @property
    def is_complete(self):
        return self._complete

    @property
    def min_route(self):
        return self._min_route

    def run(self):
        try:
            self._run()
        except Exception as e:
            print("Unexpected error during orienteering planning:", e)
            self.error_code = ERR_UNEXPECTED
            self.error_args = []
        self.progress = 100.0
        self._complete = True

    def _run(self):
        # Local imports: avoids a circular import chain (orienteering_router
        # imports from ortools_router, which imports segment_distance from
        # this module).
        from orienteering_router import plan_orienteering_route
        from route_cleanup import remove_redundant_spurs

        status, path, tiles = plan_orienteering_route(
            self.router, self.start_loc, self.visited_tiles, self.budget_km, time_limit_s=75
        )
        if self._exit:
            self.error_code = ERR_ABORT_REQUEST
            return
        if status != "success":
            self.error_code = ERR_ROUTE_ERROR
            self.error_args = ""
            return

        start_node = self.router.find_node(*self.start_loc)
        path = remove_redundant_spurs(self.router, path, tiles, {start_node})
        self.selected_tiles = tiles
        self._min_route = Route(path, router=self.router)


class RouteServer(object):
    def __init__(self):
        self.stored_tiles = {}
        self.router = None
        self.myRouter = None
        self.mode = None
        self.thread = None

    def start_route(self, mode, start_loc, end_loc, tiles, waypoints=None, config=None, thread=True,
                     gravel_tiles=None):
        if config is None:
            config = {}
        if waypoints is None:
            waypoints = {}
        print(tiles)
        print(waypoints)

        if thread and self.myRouter and not self.myRouter.is_complete:
            print("Abord previous route...")
            self.myRouter.abort()
            self.thread.join()
            print("   ...OK")
        if mode != self.mode:
            self.mode = mode
            self.stored_tiles = {}
            self.router = OsmnxDatastore(mode, cache_dir=str(Path.home().joinpath('.osmnx_cache')))
        coord_dict = CoordDict(self.router)

        # Download/cache one region up front covering start, end and every
        # selected tile - otherwise the many small get_area/get_area_rect
        # calls tile.get_entry_points makes per tile would each try to pull
        # their own (possibly overlapping) region.
        preload_points = [start_loc, end_loc] + list(waypoints)
        for t in tiles:
            if isinstance(t, str) and '_' in t:
                tile = Tile(t)
                preload_points += [(tile.latN, tile.lonW), (tile.latS, tile.lonE)]
        self.router.preload_region(preload_points)

        start_point = coord_dict.get(*start_loc)
        end_point = coord_dict.get(*end_loc)
        ways_points = [coord_dict.get(*wp) for wp in waypoints]
        print("Ways_points")
        print(ways_points)

        self.myRouter = MyRouter(self.router, start_point, end_point, tiles, ways_points, config,
                                  gravel_tiles=gravel_tiles)
        if thread:
            self.thread = threading.Thread(target=self.myRouter.run)
            # Background thread will finish with the main program
            self.thread.setDaemon(True)
            # Start YourLedRoutine() in a separate thread
            self.thread.start()

        else:
            self.myRouter.run()

        return self.myRouter, self.is_complete, self.route

    def start_orienteering(self, mode, start_loc, budget_km, visited_tiles, thread=True):
        """Distance-budgeted planning instead of a fixed tile set - see
        OrienteeringRunner. Shares the same self.myRouter slot as
        start_route() (only one route computation happens per session at a
        time either way), so the existing /route_status polling endpoint
        works unchanged for this too.
        """
        if thread and self.myRouter and not self.myRouter.is_complete:
            print("Abord previous route...")
            self.myRouter.abort()
            self.thread.join()
            print("   ...OK")
        if mode != self.mode:
            self.mode = mode
            self.stored_tiles = {}
            self.router = OsmnxDatastore(mode, cache_dir=str(Path.home().joinpath('.osmnx_cache')))

        self.myRouter = OrienteeringRunner(self.router, start_loc, visited_tiles, budget_km)
        if thread:
            self.thread = threading.Thread(target=self.myRouter.run)
            self.thread.setDaemon(True)
            self.thread.start()
        else:
            self.myRouter.run()

        return self.myRouter, self.is_complete, self.route

    @property
    def progress(self):
        return self.myRouter.progress

    @property
    def route(self):
        return self.myRouter.min_route

    @property
    def is_complete(self):
        if not self.myRouter: return True
        return self.myRouter.is_complete

    def abort(self):
        if self.myRouter:
            self.myRouter.abort()


if __name__ == '__main__':
    from pprint import pprint
    # import time
    # tiles_to_kml(['8251_5613', '8251_5614', '8249_5615'], "debug/test.kml", "test")
    rs = RouteServer()
    # print(computeMissingKml(open("missing_tiles.kml", "rb")))

    pprint(rs.start_route('roadcycle', [49.1605622003275, 1.336576378098009],
                          [49.213220722909014, 1.3079838625541165],
                          [],#['8240_5610'],
                          waypoints=[(49.213220722909014, 1.3079838625541165)],
                          config={'turnaround_cost':0.0, 'loop_cost_factor': 0.0}, thread=False)[2].route)

    # print(rs.start_route([49.250775603162886,1.4452171325683596],
    #                     [49.250775603162886,1.4452171325683596],
    #                     ["8257_5607", "8257_5610"], thread=False).min_route.routeLatLons)
    # pprint(minDists)
    # #print(rs.start_route([49.250775603162886,1.4452171325683596],
    #                      [49.250775603162886,1.4452171325683596],
    #                      [205,206], thread=False).min_route.getCoords(rs.myRouter.router))
    # print(rs.start_route([49.250775603162886,1.4452171325683596],
    #                     [49.250775603162886,1.4452171325683596],
    #                     [-1], thread=False).min_route.getCoords(rs.myRouter.router))

    # start_time = time.time()
    # rs.start_route([49.01467940545091,1.389772879538316],
    #               [49.00386989926282,1.3952660758713222], [546,580], thread=False)
    # compute_time = time.time()-start_time
    # print("compute time:", compute_time)
    # start_time = time.time()
    # print(rs.start_route([49.01467940545091,1.389772879538316],
    #                     [49.00386989926282,1.3952660758713222],
    #                     [546,580], thread=False).min_route.getCoords(rs.myRouter.router))
    # compute_time = time.time()-start_time
    # print("compute time:", compute_time)

    # myRouter = rs.start_route([49.01467940545091,1.389772879538316],
    #                          [49.00386989926282,1.3952660758713222], [546,580], thread=True)
    # while not myRouter.isComplete:
    # pass
    # print(myRouter.min_route.getCoords(rs.myRouter.router))
