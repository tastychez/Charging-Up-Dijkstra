"""Geographic distance estimates, in miles, for A* search."""

from math import atan2, cos, radians, sin, sqrt

# Same mean Earth radius used by OSMnx for its great-circle distances.
EARTH_RADIUS_MILES = 6_371_009 / 1609.344


def haversine_miles(lat1, lon1, lat2, lon2):
    """Estimate surface distance between two latitude/longitude points.

    Inputs are decimal degrees. The result is miles along a spherical Earth,
    rather than driving distance along roads.
    """
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1

    a = sin(delta_lat / 2) ** 2
    a += cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    a = max(0.0, min(1.0, a))  # Protect against tiny rounding errors.

    angle = 2 * atan2(sqrt(a), sqrt(1 - a))
    return EARTH_RADIUS_MILES * angle


def estimate_remaining_miles(graph, node, goal):
    """Read the repo's x/y coordinates and estimate distance to the goal."""
    current = graph.nodes[node]
    destination = graph.nodes[goal]
    return haversine_miles(
        current["y"], current["x"],  # y = latitude; x = longitude.
        destination["y"], destination["x"],
    )
