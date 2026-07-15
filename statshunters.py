import argparse
import os
import json
from urllib.request import urlretrieve
from utils import retry
from pathlib import Path
from tile import Tile
import re
from shapely.ops import unary_union
from fastkml import kml


@retry(Exception, tries=6, delay=60, backoff=2)
def myurlretrieve(url, filename=None, reporthook=None, data=None):
    return urlretrieve(url, filename, reporthook, data)


_SHARE_URL_RE = re.compile(r'^(https?://(?:www\.)?statshunters\.com/share/([A-Za-z0-9]+))', re.IGNORECASE)


def _normalize_share_url(sharelink_url):
    # Users paste all sorts of variants of the same sharelink: trailing
    # slash, a "/activities" suffix picked up from the browser address bar
    # while viewing the shared activity list, query params, ... Anything
    # after ".../share/<id>" is not part of the link and must be stripped
    # before it's used both as the on-disk cache key (statshunters_path())
    # and as the base for the real API request (get_statshunters_activities()).
    #
    # The host and id are deliberately validated, not just stripped: this
    # value ends up both as a directory name (statshunters_path() below)
    # and as the base of a URL this server itself fetches
    # (get_statshunters_activities()'s myurlretrieve() call). An earlier
    # version accepted *any* host and fell back to using the raw,
    # unvalidated input when the loose regex didn't match - which allowed
    # a crafted "url" query param to (a) make the server fetch arbitrary
    # attacker-chosen hosts (SSRF) and (b) reach a share id of exactly
    # ".." (input containing no further "/"), making
    # Path(folder).joinpath(index) resolve one directory above the
    # intended cache folder. Rejecting anything that isn't a genuine
    # statshunters.com share link closes both at the source.
    match = _SHARE_URL_RE.match(sharelink_url.strip())
    if not match:
        raise ValueError("Not a statshunters.com share link")
    return match.group(1)


def _share_id(sharelink_url):
    return _SHARE_URL_RE.match(_normalize_share_url(sharelink_url)).group(2)


def statshunters_path(sharelink_url, folder):
    # Re-derived from the already-validated, alphanumeric-only share id
    # rather than sharelink_url.split('/')[-1]) - defense in depth, so a
    # future loosening of _SHARE_URL_RE can't reopen the directory-escape
    # path outlined above.
    index = _share_id(sharelink_url)
    activities_path = Path(folder).joinpath(index)
    activities_path.mkdir(parents=True, exist_ok=True)
    return activities_path


def get_statshunters_activities(sharelink_url, folder, full=False):
    sharelink_url = _normalize_share_url(sharelink_url)
    activities_path = statshunters_path(sharelink_url, folder)
    page = 1

    if not full:
        while activities_path.joinpath("activities_{}.json".format(page + 2)).exists():
            page += 1

    while True:
        filepath = activities_path.joinpath("activities_{}.json".format(page))
        url = sharelink_url + "/api/activities?page={0}".format(page)
        print("Get page {} ({})".format(page, url))
        myurlretrieve(url, filepath)
        with open(filepath) as f:
            d = json.load(f)
            if len(d['activities']) == 0:
                break
        page += 1

    return activities_path


def _iter_activities(activities_dir):
    directory = os.fsencode(activities_dir)
    for file in os.listdir(directory):
        filename = os.fsdecode(file)
        if filename.endswith(".json"):
            with open(os.path.join(activities_dir, filename)) as f:
                d = json.load(f)
                for activity in d['activities']:
                    yield activity


def tiles_from_activities(activities_dir, activity_type=None):
    # Get tiles from activities files from statshunters, optionally
    # restricted to a single activity type. activity_type comes from a fixed
    # dropdown in the UI, not free-form user text - see activity_filter_options().
    tiles = []

    for activity in _iter_activities(activities_dir):
        if activity_type and activity.get('type') != activity_type:
            continue
        for tile in activity['tiles']:
            uid = "{0}_{1}".format(tile['x'], tile['y'])
            if uid not in tiles:
                tiles.append(uid)
    return frozenset(tiles)


def activity_filter_options(activities_dir):
    # Distinct activity types present in the imported data, used to
    # populate the activity-type filter dropdown in the UI.
    types = set()
    for activity in _iter_activities(activities_dir):
        if activity.get('type'):
            types.add(activity['type'])
    return {'types': sorted(types)}


def getKmlFromGeom(geom):
    # 'kml:' stripped from the output because leaflet-omnivore's KML parser
    # (toGeoJSON) looks up elements by plain tag name (e.g. "Placemark",
    # "coordinates") without namespace awareness - a prefixed tag would
    # silently fail to match.
    ns = '{http://www.opengis.net/kml/2.2}'
    placemark = kml.Placemark(ns=ns, geometry=geom)
    folder = kml.Folder(ns=ns, features=[placemark])
    document = kml.Document(ns=ns, features=[folder])
    k = kml.KML(ns=ns, features=[document])
    return k.to_string().replace('kml:', '')


def compute_zones(tiles):
    tiles = set(tiles)
    clusters = []
    while True:
        if len(tiles) == 0:
            break

        for c in tiles:
            cluster = set([c])
            boundary = set([c])
            break

        tiles -= cluster

        while True:
            new_c = set()
            for tile in boundary:
                x, y = tile
                for dx, dy in adjoining:
                    if (x + dx, y + dy) in tiles:
                        new_c.add((x + dx, y + dy))
            if new_c:
                cluster |= new_c
                boundary = new_c
                tiles -= new_c
            else:
                break
        clusters.append(cluster)

    clusters.sort(key=len, reverse=True)
    return clusters


adjoining = [(1, 0), (-1, 0), (0, 1), (0, -1) ]


def compute_cluster(tiles):
    if not tiles:
        return 0
    if isinstance(list(tiles)[0], str):
        tiles = set([tuple([int(i) for i in t.split('_')]) for t in tiles])
    cluster_tiles = set()
    for (x,y) in tiles:
        for dx, dy in adjoining:
            if (x + dx, y + dy) not in tiles:
                break
        else:
            cluster_tiles.add((x, y))

    if len(cluster_tiles)==0:
        return 0
    zones = compute_zones(cluster_tiles)

    geom_z = unary_union([Tile(*t).polygon for t in zones[0]])

    return getKmlFromGeom(geom_z)


def compute_max_square(tiles):
    if not tiles:
        # No tiles at all (e.g. a well-formed but never-imported/empty
        # sharelink) - nothing to build a square from. unary_union() on an
        # empty polygon list produces a geometry fastkml can't serialize
        # ("Illegal geometry type"), so this must be caught before that,
        # consistent with compute_cluster()'s same-situation return value.
        return 0

    def is_square(x, y, m):
        for dx in range(m):
            for dy in range(m):
                uid = "{}_{}".format(x+dx, y+dy)
                if uid not in tiles : return False
        return True

    max_square = 0
    x_max = 0
    y_max = 0
    for tile in tiles:
        x = int(tile.split('_')[0])
        y = int(tile.split('_')[1])
        while is_square(x, y, max_square+1):
            max_square += 1
            x_max = x
            y_max = y
    tiles = set()
    for x in range(x_max, x_max+max_square):
        for y in range(y_max, y_max+max_square):
            tiles.add(Tile("{}_{}".format(x,y)))
    geom_z = unary_union([t.polygon for t in tiles])
    return getKmlFromGeom(geom_z)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Compute exploration ratio of a zone')
    parser.add_argument('-s', '--sharelink', dest="sharelink", help="Stathunters share link to recover data")
    args = parser.parse_args()

    sharelink = vars(args)['sharelink']

    index = get_statshunters_activities(sharelink)

    tiles = tiles_from_activities(index)

    print(compute_max_square(tiles))
