"""Haversine and Manhattan estimates in miles, plus a consistency check.

Raw Manhattan is a geographic approximation, not automatically a lower bound
on driving distance. prepare_heuristic scales either estimate when necessary
so it is consistent with the supplied charging graph's actual edge weights.
"""

from dataclasses import dataclass
from math import atan2, cos, isfinite, radians, sin, sqrt

EARTH_RADIUS_MILES = 6_371_009 / 1609.344


def validate_coordinates(latitude, longitude):
    if not isfinite(latitude) or not -90 <= latitude <= 90:
        raise ValueError("Latitude must be a finite number between -90 and 90.")
    if not isfinite(longitude) or not -180 <= longitude <= 180:
        raise ValueError("Longitude must be a finite number between -180 and 180.")


def haversine_miles(lat1, lon1, lat2, lon2):
    """Great circle distance on a spherical Earth; inputs are decimal degrees."""
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    a = sin(delta_lat / 2) ** 2
    a += cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    a = max(0.0, min(1.0, a))
    return EARTH_RADIUS_MILES * 2 * atan2(sqrt(a), sqrt(1 - a))


def manhattan_miles(lat1, lon1, lat2, lon2):
    """Approximate north/south + east/west distance in miles.
    Use prepare_heuristic() before A* to check and scale as needed.
    """
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    delta_lon = atan2(sin(lon2 - lon1), cos(lon2 - lon1))  # Wrap at +/-180 degrees.
    north_south = EARTH_RADIUS_MILES * abs(lat2 - lat1)
    east_west = EARTH_RADIUS_MILES * abs(cos(lat2) * delta_lon)
    return north_south + east_west


def estimate_remaining_miles(graph, node, goal, method="haversine"):
    """Compatibility helper for the original NetworkX demo (x=lon, y=lat).

    This returns the raw formula. The corridor runner instead calls
    prepare_heuristic to check the actual graph before searching.
    """
    functions = {"haversine": haversine_miles, "manhattan": manhattan_miles}
    if method not in functions:
        raise ValueError("Heuristic must be 'haversine' or 'manhattan'.")
    current, destination = graph.nodes[node], graph.nodes[goal]
    return functions[method](current["y"], current["x"], destination["y"], destination["x"])


@dataclass
class PreparedHeuristic:
    method: str
    raw_values: dict
    values: dict
    scale: float
    raw_inconsistent_edges: int

    def __call__(self, node):
        return self.values[node]


def prepare_heuristic(graph, coordinates, goal, method="haversine"):
    """Prepare consistent h values for {node: {neighbor: miles}} in O(V+E).

    Choose alpha <= 1 such that for EVERY edge u -> v:
        alpha * (raw_h[u] - raw_h[v]) <= weight(u, v).
    Then h[u] <= weight(u, v) + h[v]. With h[goal]=0, this guarantees an
    admissible estimate for the supplied graph. No shortest-path oracle is used.
    """
    functions = {"haversine": haversine_miles, "manhattan": manhattan_miles}
    if method not in functions:
        raise ValueError("Heuristic must be 'haversine' or 'manhattan'.")
    if goal not in graph:
        raise ValueError("The destination must be in the graph.")
    for node in graph:
        if node not in coordinates:
            raise ValueError(f"Missing coordinates for {node!r}.")
        validate_coordinates(*coordinates[node])

    goal_lat, goal_lon = coordinates[goal]
    raw = {node: functions[method](*coordinates[node], goal_lat, goal_lon) for node in graph}
    scale = 1.0
    inconsistent_edges = 0
    for source, neighbors in graph.items():
        for target, weight in neighbors.items():
            if target not in graph:
                raise ValueError(f"Neighbor {target!r} is missing from the graph.")
            if not isfinite(weight) or weight < 0:
                raise ValueError("Edge distances must be finite and nonnegative.")
            decrease = raw[source] - raw[target]
            if decrease > weight + 1e-9:
                inconsistent_edges += 1
            if decrease > 0:
                scale = min(scale, weight / decrease)
    if scale < 1:
        scale *= 1 - 1e-12  # Small numerical margin below the tightest edge bound.
    values = {node: scale * value for node, value in raw.items()}
    return PreparedHeuristic(method, raw, values, scale, inconsistent_edges)
