"""Battery feasibility belongs in the charging graph, before A* searches it."""

from dataclasses import dataclass
from math import isfinite


@dataclass
class BatteryLeg:
    source: str
    target: str
    miles: float
    range_before: float
    range_on_arrival: float
    range_after_stop: float
    recharged: bool


def validate_ranges(starting_range, full_range):
    if not isfinite(full_range) or full_range <= 0:
        raise ValueError("Full-charge range must be finite and greater than zero.")
    if not isfinite(starting_range) or not 0 <= starting_range <= full_range:
        raise ValueError("Starting range must be between zero and full-charge range.")


def build_charging_graph(road_miles, source, target, full_range,
                         starting_range=None, chargers=None):
    """Build {stop: {next_stop: driving_miles}} in O(N^2) for a dense table.

    road_miles is the team's directed all-pairs driving-distance table.
    Missing/None entries mean no known drivable connection. Every intermediate
    vertex must be a charging location. Selected chargers refill to full range.
    Passing a station on an underlying road leg never forces a charging stop.
    The start has no incoming edges and the destination has no outgoing edges.
    """
    starting_range = full_range if starting_range is None else starting_range
    validate_ranges(starting_range, full_range)
    if source not in road_miles or target not in road_miles:
        raise ValueError("Start and destination must exist in the road-distance table.")
    chargers = set(road_miles) if chargers is None else set(chargers)
    if chargers - road_miles.keys():
        raise ValueError("Every charger must exist in the road-distance table.")
    allowed = chargers | {source, target}
    graph = {node: {} for node in road_miles if node in allowed}
    for first in graph:
        if first == target:
            continue
        available = starting_range if first == source else full_range
        for second in graph:
            if second == first or second == source:
                continue
            miles = road_miles[first].get(second)
            if miles is None:
                continue
            miles = float(miles)
            if not isfinite(miles) or miles < 0:
                raise ValueError("Driving distances must be finite and nonnegative.")
            if miles <= available:
                graph[first][second] = miles
    return graph


def battery_legs(stops, graph, starting_range, full_range):
    """Explain range consumption/refills along an already feasible route."""
    validate_ranges(starting_range, full_range)
    remaining = starting_range
    legs = []
    for index, (source, target) in enumerate(zip(stops, stops[1:])):
        miles = graph[source][target]
        if miles > remaining + 1e-9:
            raise ValueError("A selected leg exceeds the remaining range.")
        arrival = max(0.0, remaining - miles)
        recharged = index < len(stops) - 2  # Intermediate stops are chargers.
        after_stop = full_range if recharged else arrival
        legs.append(BatteryLeg(source, target, miles, remaining, arrival, after_stop, recharged))
        remaining = after_stop
    return legs


def demo_data():
    """Offline five-city example. Distances are illustrative, not measured roads."""
    coordinates = {
        "Cambridge": (42.3736, -71.1097), "Boston": (42.3601, -71.0589),
        "Medford": (42.4184, -71.1062), "Lynn": (42.4668, -70.9495),
        "Salem": (42.5195, -70.8967),
    }
    names = list(coordinates)
    # Precomputed distances through the original demo's illustrative roads.
    rows = [[0, 4, 5, 17, 23], [4, 0, 9, 14, 20], [5, 9, 0, 12, 18],
            [17, 14, 12, 0, 6], [23, 20, 18, 6, 0]]
    road_miles = {name: dict(zip(names, row)) for name, row in zip(names, rows)}
    chargers = {"Boston", "Medford", "Lynn"}
    return coordinates, road_miles, chargers, "Cambridge", "Salem"
