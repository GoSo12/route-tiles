"""Road-type weight tables per travel mode, keyed by OSM `highway` tag.

Historical note: this module used to be a vendored copy of pyroutelib3
(https://github.com/MKuranowski/pyroutelib3, GPLv3) - an OSM-file parser and
router. Since the osmnx/NetworkX migration (see osmnx_datastore.py), none of
that parsing/routing code is used anymore; only the TYPES weight tables
below (locally authored for this project, not part of upstream
pyroutelib3) are still imported. The GPLv3-derived routing code has been
removed accordingly.
"""


def weight_primary_roadcycle(t):
    maxspeed = t.get("maxspeed", "80")
    if isinstance(maxspeed, list):
        maxspeed = maxspeed[0]
    try:
        w = int(str(maxspeed).split()[0])
    except (ValueError, IndexError):
        w = 80
    if w <= 50:
        return 1
    if w <= 70:
        return 0.75
    if w <= 80:
        return 0.5
    return 0.25


def filter_asphalt(t):
    # Allow asphalt path and zebra crossing
    if t.get("surface") in ['asphalt']:
        return 1
    if t.get("footway") in ['crossing']:
        return 1
    if t.get("crossing") in ['zebra']:
        return 1
    return 0


TYPES = {
    "roadcycle": {
        "weights": {"primary": weight_primary_roadcycle, "secondary": 1, "tertiary": 1,
                    "unclassified": 0.9, "residential": 0.9, "living_street": 0.9, "cycleway": 0.9,
                    "footway": lambda t:filter_asphalt(t)*0.85, "path": lambda t:filter_asphalt(t)*0.85},
        "access": ["access", "vehicle", "bicycle"],
        "transport": "bicycle"
    },
    "gravelbike": {
        # Unlike roadcycle (which excludes track and only allows path if
        # asphalt), a gravel bike is happy on unpaved tracks/paths and
        # actively prefers them over fast/busy roads.
        "weights": {"trunk": 0.1, "primary": weight_primary_roadcycle, "secondary": 0.8, "tertiary": 0.9,
                    "unclassified": 1, "residential": 0.9, "living_street": 0.8, "service": 0.9,
                    "track": 1.0, "bridleway": 0.7, "footway": 0.6, "path": 0.9, "cycleway": 0.8},
        "access": ["access", "vehicle", "bicycle"],
        "transport": "bicycle"
    },
    "road_foot": {
        "weights": {"trunk": 0.3, "primary": weight_primary_roadcycle, "secondary": 1, "tertiary": 1,
                    "unclassified": 1, "residential": 1, "living_street": 1, "track": 0.1, "service": 1,
                    "bridleway": 0.1, "footway": filter_asphalt, "path": filter_asphalt, "steps": 1},
        "access": ["access", "foot"],
        "transport": "foot"
    },
    "foot": {
        "weights": {"trunk": 0.3, "primary": weight_primary_roadcycle, "secondary": 0.9, "tertiary": 1,
                    "unclassified": 1, "residential": 1, "living_street": 1, "track": 1, "service": 1,
                    "bridleway": 1, "footway": 1, "cycleway": 0.9, "path": 1, "steps": 1},
        "access": ["access", "foot"],
        "transport": "foot"
    },
    "trail": {
        "weights": {"trunk": 0.1, "primary": 0.3, "secondary": 0.6, "tertiary": 0.7,
                    "unclassified": 0.7, "residential": 0.8, "living_street": 0.8, "track": 0.9, "service": 0.8,
                    "bridleway": 0.9, "footway": 0.9, "path": 1, "steps": 1, "cycleway": 0.85},
        "access": ["access", "foot"],
        "transport": "foot"
    },
    "trail2": {
        "weights": {"trunk": 0.1, "primary": 0.1, "secondary": 0.1, "tertiary": 0.1, "service": 0.1,
                    "unclassified": 0.1, "residential": 0.1, "living_street": 0.1, "track": 1.0,
                    "bridleway": 0.9, "footway": 1.0, "path": 1, "steps": 1, "cycleway": 0.9},
        "access": ["access", "foot"],
        "transport": "foot"
    }
}
