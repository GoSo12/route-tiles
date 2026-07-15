import http.server
import json
import os
import secrets
import socketserver
import string
import struct
import zlib
import argparse
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path
from pprint import pprint
from urllib import parse

from tilesrouter import RouteServer, latlons_to_gpx
from tile import tiles_to_kml
from statshunters import get_statshunters_activities, tiles_from_activities, activity_filter_options, compute_max_square, compute_cluster, statshunters_path
from scoring import find_best_square_completion
from route_timing import estimate_time


PORT = 8000

# Bundled sample tile-hunting history (not user data - see demo_data/README
# if present) so the app can be tried/demoed without a real Statshunters
# account. Kept outside data/ (gitignored, reserved for real per-user
# import caches) so it actually ships with the repo.
DEMO_DATA_FOLDER = Path(__file__).parent.joinpath('demo_data')

sessionDict = {}
chars = string.ascii_letters + string.digits


class SessionElement(object):
    """Arbitrary objects, referenced by the session id"""

    def __init__(self):
        self.routeServer = RouteServer()
        self.last_access = datetime.now()

    def refresh(self):
        self.last_access = datetime.now()


def check_sessions():
    for session_id in list(sessionDict):
        session = sessionDict[session_id]
        if session.routeServer.is_complete:
            timeout = timedelta(0, 10*60) # 10min
        else:
            timeout = timedelta(0, 10*60) # 10min

        if datetime.now() - session.last_access > timeout:
            print("Remove session ", session_id)
            if not session.routeServer.is_complete:
                print("  abort previous routing")
                session.routeServer.myRouter.abort()
            sessionDict.pop(session_id)



def generate_random(length):
    """Return a random string of specified length (used for session id's).

    secrets.choice(), not random.choice() - session ids are an
    unauthenticated bearer token (whoever holds one can read/abort that
    session's in-progress route search), so they need to come from a CSPRNG
    rather than Python's default Mersenne Twister random module, which is
    predictable given enough observed output.
    """
    return ''.join([secrets.choice(chars) for _ in range(length)])


class RouteHttpServer(http.server.SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = None
        self.sessionId = None

    def end_headers(self):
        # Dev server under active iteration: index.html/index.js change
        # often and are served without cache-busting filenames, so a stale
        # browser cache of them is a recurring source of "my fix isn't
        # showing up" confusion. Disabling caching outright costs nothing
        # here (purely local, low-traffic tool).
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def do_GET_request(self):
        parsed_path = parse.urlparse(self.path)
        message_parts = [
            'CLIENT VALUES:',
            'client_address={} ({})'.format(
                self.client_address,
                self.address_string()),
            'command={}'.format(self.command),
            'path={}'.format(self.path),
            'real path={}'.format(parsed_path.path),
            'query={}'.format(parsed_path.query),
            'request_version={}'.format(self.request_version),
            '',
            'SERVER VALUES:',
            'server_version={}'.format(self.server_version),
            'sys_version={}'.format(self.sys_version),
            'protocol_version={}'.format(self.protocol_version),
            '',
            'HEADERS RECEIVED:',
        ]
        for name, value in sorted(self.headers.items()):
            message_parts.append(
                '{}={}'.format(name, value.rstrip())
            )
        message_parts.append('')
        message = '\r\n'.join(message_parts)
        self.send_response(200)
        self.send_header('Content-Type',
                         'text/plain; charset=utf-8')
        self.end_headers()
        self.wfile.write(message.encode('utf-8'))

    def _activity_filter_from_qs(self, qs):
        # Fixed dropdown value from the UI (see activity_filter_options()),
        # never a free-form expression - deliberately not passed to eval().
        return qs['type'][0] if qs.get('type', [''])[0] else None

    def _activities_folder(self, qs, allow_fetch=False):
        """Resolve which activities folder a request should read from -
        the bundled demo dataset if demo=1 is set, otherwise the real
        Statshunters share link in url= (validated by statshunters_path()/
        get_statshunters_activities(), which raise ValueError for anything
        that isn't a genuine statshunters.com link - see UPDATES.md for
        why that validation exists).

        Demo mode deliberately short-circuits before url= is even looked
        at - it never touches network fetching or the url-validation path,
        so it can't reopen that surface no matter what a client sends
        alongside demo=1.
        """
        if qs.get('demo', ['0'])[0] == '1':
            return DEMO_DATA_FOLDER
        url = qs['url'][0]
        data_folder = Path(__file__).parent.joinpath('data')
        if allow_fetch:
            return get_statshunters_activities(url, data_folder)
        return statshunters_path(url, data_folder)

    def do_GET_statshunters(self):
        parsed_path = parse.urlparse(self.path)
        qs = parse.parse_qs(parsed_path.query, keep_blank_values=True)
        activity_type = self._activity_filter_from_qs(qs)

        try:
            folder = self._activities_folder(qs, allow_fetch=True)
        except ValueError as e:
            self.wfile.write(json.dumps({'status': 'Fail', 'message': str(e)}).encode('utf-8'))
            return

        tiles = tiles_from_activities(folder, activity_type=activity_type)

        kml_max_square = compute_max_square(tiles)
        kml_cluster = compute_cluster(tiles)

        self.wfile.write(json.dumps({'status': 'OK',
                                     'tiles': list(tiles),
                                     'maxSquare': kml_max_square,
                                     'cluster': kml_cluster,
                                     'filterOptions': activity_filter_options(folder)}).encode('utf-8'))


    def do_GET_statshunters_filter(self):
        parsed_path = parse.urlparse(self.path)
        qs = parse.parse_qs(parsed_path.query, keep_blank_values=True)
        activity_type = self._activity_filter_from_qs(qs)

        try:
            folder = self._activities_folder(qs)
        except ValueError as e:
            self.wfile.write(json.dumps({'status': 'Fail', 'message': str(e)}).encode('utf-8'))
            return

        tiles = tiles_from_activities(folder, activity_type=activity_type)

        kml_max_square = compute_max_square(tiles)

        kml_cluster = compute_cluster(tiles)

        self.wfile.write(json.dumps({'status': 'OK',
                                     'tiles': list(tiles),
                                     'maxSquare': kml_max_square,
                                     'cluster': kml_cluster,
                                     'filterOptions': activity_filter_options(folder)}).encode('utf-8'))

    def do_GET_scoring(self):
        parsed_path = parse.urlparse(self.path)
        qs = parse.parse_qs(parsed_path.query, keep_blank_values=True)
        activity_type = self._activity_filter_from_qs(qs)

        try:
            folder = self._activities_folder(qs)
        except ValueError as e:
            self.wfile.write(json.dumps({'status': 'Fail', 'message': str(e)}).encode('utf-8'))
            return

        tiles = tiles_from_activities(folder, activity_type=activity_type)

        self.wfile.write(json.dumps({'status': 'OK',
                                     'maxSquareCompletion': find_best_square_completion(tiles)}).encode('utf-8'))

    def do_GET_estimate_route_time(self):
        parsed_path = parse.urlparse(self.path)
        qs = parse.parse_qs(parsed_path.query, keep_blank_values=True)
        solver = qs['solver'][0]
        param_value = float(qs['param'][0])

        self.wfile.write(json.dumps({'status': 'OK',
                                     'estimatedSeconds': estimate_time(solver, param_value)}).encode('utf-8'))

    def do_GET_start_route(self):
        parsed_path = parse.urlparse(self.path)
        qs = parse.parse_qs(parsed_path.query, keep_blank_values=True)
        pprint(qs)
        start = [float(qs['start[]'][0]), float(qs['start[]'][1])]
        end = [float(qs['end[]'][0]), float(qs['end[]'][1])]
        mode = qs['mode'][0]
        turnaround_cost = float(qs.get('turnaroundCost', ['0'])[0])
        if 'tiles[]' in qs:
            tiles = qs['tiles[]']
            for i in range(len(tiles)):
                if '_' not in tiles[i]:
                    tiles[i] = int(tiles[i])
        else:
            tiles = []

        waypoints = []
        if 'waypoints[0][]' in qs:
            wpi = 0
            while 'waypoints[{}][]'.format(wpi) in qs:
                waypoints.append([float(v) for v in qs['waypoints[{}][]'.format(wpi)]])
                wpi += 1
            pprint(waypoints)

        gravel_tiles = qs.get('gravelTiles[]', [])

        answer = {'sessionId': self.sessionId}

        router, message, info = self.session.routeServer.start_route(mode, start, end, tiles, waypoints=waypoints, config={'turnaround_cost':turnaround_cost}, gravel_tiles=gravel_tiles)

        if router:
            answer['status'] = "OK"
            if self.session.routeServer.is_complete:
                answer['state'] = 'complete'
            else:
                answer['state'] = 'searching'

            route = self.session.routeServer.route
            if route:
                crc = "{:X}".format(zlib.crc32(struct.pack(">{}Q".format(len(route.route)), *route.route)))

                answer['findRouteId'] = crc
                answer['length'] = route.length
                answer['route'] = route.routeLatLons
        else:
            answer['status'] = "Fail"
            answer['message'] = message
            answer['tiles'] = info

        self.wfile.write(json.dumps(answer).encode('utf-8'))

    def do_GET_start_orienteering(self):
        parsed_path = parse.urlparse(self.path)
        qs = parse.parse_qs(parsed_path.query, keep_blank_values=True)
        pprint(qs)
        start = [float(qs['start[]'][0]), float(qs['start[]'][1])]
        budget_km = float(qs['budgetKm'][0])
        mode = qs['mode'][0]
        activity_type = self._activity_filter_from_qs(qs)

        try:
            folder = self._activities_folder(qs)
        except ValueError as e:
            self.wfile.write(json.dumps({'status': 'Fail', 'message': str(e),
                                          'sessionId': self.sessionId}).encode('utf-8'))
            return
        visited_tiles = tiles_from_activities(folder, activity_type=activity_type)

        answer = {'sessionId': self.sessionId}

        router, _, _ = self.session.routeServer.start_orienteering(mode, start, budget_km, visited_tiles)

        answer['status'] = "OK"
        answer['state'] = 'complete' if self.session.routeServer.is_complete else 'searching'

        self.wfile.write(json.dumps(answer).encode('utf-8'))

    def do_GET_route_status(self):
        parsed_path = parse.urlparse(self.path)
        qs = parse.parse_qs(parsed_path.query, keep_blank_values=True)
        answer = {'status': "OK"}

        if self.session.routeServer.myRouter.error_code==0:
            if self.session.routeServer.is_complete:
                answer['state'] = 'complete'
            else:
                answer['state'] = 'searching'
            answer['progress'] = self.session.routeServer.progress
            route = self.session.routeServer.route
            if route:
                crc = "{:X}".format(zlib.crc32(struct.pack(">{}Q".format(len(route.route)), *route.route)))

                if self.session.routeServer.is_complete or 'findRouteId' not in qs or crc != qs['findRouteId'][0]:
                    answer['findRouteId'] = crc
                    answer['length'] = route.length
                    answer['route'] = route.routeLatLons
                    selected_tiles = getattr(self.session.routeServer.myRouter, 'selected_tiles', None)
                    if selected_tiles is not None:
                        answer['selectedTiles'] = selected_tiles
        else:
            answer['status'] = 'Fail'
            answer['error_code'] = self.session.routeServer.myRouter.error_code
            answer['error_args'] =self.session.routeServer.myRouter.error_args


        answer['sessionId'] = self.sessionId
        self.wfile.write(json.dumps(answer).encode('utf-8'))

    def do_GET_abort_route(self):
        # Note: for the OR-Tools-based solvers, this only takes effect at
        # the next checkpoint (between tiles, or once the current blocking
        # OR-Tools solve call returns) - it can't interrupt a solve already
        # in progress mid-call.
        self.session.routeServer.abort()
        self.wfile.write(json.dumps({'status': 'OK', 'sessionId': self.sessionId}).encode('utf-8'))

    def do_GET_generate_gpx(self):
        parsed_path = parse.urlparse(self.path)
        qs = parse.parse_qs(parsed_path.query, keep_blank_values=True)

        gpx_name = qs.get('name', [""])[0]
        if gpx_name == "":
            gpx_name = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
        gpx_file_name = gpx_name
        if not gpx_file_name.upper().endswith(".GPX"):
            gpx_file_name += ".gpx"
        if "\\" in gpx_file_name or "/" in gpx_file_name:
            answer = {'status': "Fail", 'message': "wrong filename"}
        elif not self.session.routeServer.myRouter:
            answer = {'status': "Fail", 'message': "No route"}
        elif self.session.routeServer.myRouter.generate_gpx(
                os.path.join(self.directory, 'gpx', gpx_file_name), gpx_name):
            answer = {'status': "OK", 'path': 'gpx/' + gpx_file_name}
        else:
            answer = {'status': "Fail", 'message': "error generating GPX"}
        answer['sessionId'] = self.sessionId
        self.wfile.write(json.dumps(answer).encode('utf-8'))

    def do_GET_generate_kml_tiles(self):
        parsed_path = parse.urlparse(self.path)
        qs = parse.parse_qs(parsed_path.query, keep_blank_values=True)

        file_name = qs.get('name', [""])[0]
        if 'tiles[]' in qs:
            tiles = qs['tiles[]']
            for i in range(len(tiles)):
                if '_' not in tiles[i]:
                    tiles[i] = int(tiles[i])
        else:
            tiles = []

        if file_name == "":
            file_name = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
        kml_file_name = file_name
        if not kml_file_name.upper().endswith(".KML"):
            kml_file_name += ".kml"
        if "\\" in kml_file_name or "/" in kml_file_name:
            answer = {'status': "Fail", 'message': "wrong filename"}
        elif tiles_to_kml(tiles, os.path.join(self.directory, 'gpx', kml_file_name), file_name):
            answer = {'status': "OK", 'path': 'gpx/' + kml_file_name}
        else:
            answer = {'status': "Fail", 'message': "error generating KML"}
        self.wfile.write(json.dumps(answer).encode('utf-8'))

    def _set_headers(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()

    def do_GET(self):
        print(self.path)
        parsed_path = parse.urlparse(self.path)

        get_action_name = 'do_GET_' + parsed_path.path[1:]
        if hasattr(self, get_action_name):
            self.session = self.get_session()
            self._set_headers()
            method = getattr(self, get_action_name)
            method()
        else:
            super().do_GET()

    def do_POST(self):
        print(self.path)
        parsed_path = parse.urlparse(self.path)
        self.session = self.get_session()

        if parsed_path.path == "/generate_gpx":
            self._set_headers()
            pprint(dict(self.headers))
            length = int(self.headers['Content-Length'])
            data = self.rfile.read(length).decode("utf-8")
            qs = parse.parse_qs(data, keep_blank_values=True)
            gpx_name = str(qs.get('name', [""])[0])
            coords = [x.split(',') for x in qs['points[]']]
            if gpx_name == "":
                gpx_name = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
            gpx_file_name = gpx_name
            if not gpx_file_name.upper().endswith(".GPX"):
                gpx_file_name += ".gpx"
            if "\\" in gpx_file_name or "/" in gpx_file_name:
                answer = {'status': "Fail", 'message': "wrong filename"}
            elif not coords:
                answer = {'status': "Fail", 'message': "No route"}
            elif latlons_to_gpx(coords, os.path.join(self.directory, 'gpx', gpx_file_name), gpx_name):
                answer = {'status': "OK", 'path': 'gpx/' + gpx_file_name}
            else:
                answer = {'status': "Fail", 'message': "error generating GPX"}
            self.wfile.write(json.dumps(answer).encode('utf-8'))

    def get_session(self):

        parsed_path = parse.urlparse(self.path)
        qs = parse.parse_qs(parsed_path.query, keep_blank_values=True)
        if "sessionId" in qs:
            self.sessionId = qs["sessionId"][0]
        else:
            self.sessionId = generate_random(8)
        try:
            session_object = sessionDict[self.sessionId]
        except KeyError:
            self.sessionId = generate_random(8)
            session_object = SessionElement()
            sessionDict[self.sessionId] = session_object
            print("Create session", self.sessionId)

        session_object.refresh()
        check_sessions()
        return session_object


def route_tiles_server(port):
    # Create gpx folder is not exists for gpx export
    Path(__file__).parent.joinpath('static', 'gpx').mkdir(exist_ok=True)
    Path(__file__).parent.joinpath('debug').mkdir(exist_ok=True)
    handler_class = partial(RouteHttpServer, directory=str(Path(__file__).parent.joinpath('static')))
    # Plain TCPServer processes requests strictly one at a time - a slow or
    # hung request (e.g. get_statshunters_activities() retrying against an
    # unreachable host for up to ~1h, see UPDATES.md) blocked the entire
    # server for every tab/user until it returned. ThreadingTCPServer
    # handles each request on its own thread instead.
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    socketserver.ThreadingTCPServer.daemon_threads = True
    with socketserver.ThreadingTCPServer(("", port), handler_class) as httpd:
        print("serving at port", port)
        httpd.serve_forever()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Route Tiles server')
    parser.add_argument('-p', '--port', dest="port", type=int, default=PORT, help="Server port")
    args = parser.parse_args()

    port = vars(args)['port']

    route_tiles_server(port)

