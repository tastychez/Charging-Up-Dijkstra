"""Our own Dijkstra and A*, written to plug into trip.plan_trip.

Both have the same signature as networkx.dijkstra_path(graph, source, target, weight)
and work on any NetworkX graph: graph[u] maps each neighbor v to the edge's
attributes, and d[weight] is the edge's length. Among routes of exactly equal
weight, the one with fewer legs wins.

A* needs a guess of the remaining weight that never overestimates. Every vertex in
our graphs has coordinates, and no road is shorter than the straight line between
its ends (check_graphs.py checks this), so the straight-line miles to the target
is a safe guess:

    miles: h(v) = straight-line miles from v to the target
    cost:  h(v) = straight-line miles + 10,000 x (fewest legs that could still be left)

where the fewest legs left is ceil(straight-line miles / longest allowed leg). Both
guesses are consistent (h(u) <= w(u, v) + h(v) on every edge), so A* returns the
same best route as Dijkstra after looking at fewer vertices.
"""

import heapq
import math
from itertools import count

import networkx as nx

import data

EARTH_RADIUS_MILES = 6_371_009 / data.METERS_PER_MILE  # same Earth radius OSMnx uses


def _coords(graph, node):
    """(lat, lon) of a vertex: trip/charger graphs store lat/lon, street graphs y/x."""
    d = graph.nodes[node]
    return (d["lat"], d["lon"]) if "lat" in d else (d["y"], d["x"])


def straight_line_miles(lat1, lon1, lat2, lon2):
    """Great-circle distance in miles (haversine)."""
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    a = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_RADIUS_MILES * math.asin(min(1.0, math.sqrt(a)))


def straight_line_heuristic(graph, target, weight="miles"):
    """h(v) for A*: a lower bound on the remaining `weight` from v to target.

    For weight="cost" the graph must say how long a leg can be and what each leg
    adds, in graph.graph["usable_miles"] and ["stop_cost_miles"] (trip.plan_trip sets both).
    """
    lat_t, lon_t = _coords(graph, target)
    # Shave a hair off so floating point rounding can never make h overestimate.
    margin = 1 - 1e-9
    if weight == "miles":
        return lambda v: margin * straight_line_miles(*_coords(graph, v), lat_t, lon_t)
    if weight == "cost":
        usable, stop_cost = graph.graph["usable_miles"], graph.graph["stop_cost_miles"]

        def h(v):
            miles = margin * straight_line_miles(*_coords(graph, v), lat_t, lon_t)
            return miles + stop_cost * math.ceil(miles / usable)
        return h
    raise ValueError(f"No straight-line heuristic for weight {weight!r}")


def _rebuild(prev, source, target):
    path = [target]
    while path[-1] != source:
        path.append(prev[path[-1]])
    return path[::-1]


def dijkstra_path(graph, source, target, weight="miles", stats=None):
    """Shortest path from source to target by `weight`, with Dijkstra's algorithm.

    Pass a dict as `stats` to get the number of expanded vertices and edges checked.
    """
    best = {source: (0.0, 0)}       # vertex -> (weight, legs) of best known route
    prev = {}
    settled = set()
    order = count()                 # tie-break: vertex ids mix ints and strings
    heap = [(0.0, 0, next(order), source)]
    edge_checks = 0

    while heap:
        dist, legs, _, u = heapq.heappop(heap)
        if u in settled:
            continue                # outdated heap entry
        settled.add(u)              # its distance is now final
        if u == target:
            break
        for v, d in graph[u].items():
            edge_checks += 1
            candidate = (dist + d[weight], legs + 1)
            if v not in settled and (v not in best or candidate < best[v]):
                best[v] = candidate
                prev[v] = u
                heapq.heappush(heap, (*candidate, next(order), v))

    if stats is not None:
        stats.update(expanded=len(settled), edge_checks=edge_checks)
    if target not in settled:
        raise nx.NetworkXNoPath(f"No path from {source} to {target}")
    return _rebuild(prev, source, target)


def astar_path(graph, source, target, weight="miles", heuristic=None, stats=None):
    """Shortest path from source to target by `weight`, with A*.

    Vertices come off the heap in order of f = g + h, where g is the weight so far
    and h = heuristic(v) guesses the rest. h must never overestimate; the default is
    straight_line_heuristic. With h = 0 this is exactly Dijkstra.
    """
    h = heuristic or straight_line_heuristic(graph, target, weight)
    best = {source: (0.0, 0)}       # vertex -> (g, legs) of best known route
    prev = {}
    settled = set()
    order = count()
    heap = [(h(source), 0, next(order), source, 0.0)]   # (f, legs, tie-break, vertex, g)
    edge_checks = 0

    while heap:
        _, legs, _, u, g = heapq.heappop(heap)
        if u in settled:
            continue                # outdated heap entry
        settled.add(u)
        if u == target:
            break
        for v, d in graph[u].items():
            edge_checks += 1
            candidate = (g + d[weight], legs + 1)
            if v not in settled and (v not in best or candidate < best[v]):
                best[v] = candidate
                prev[v] = u
                heapq.heappush(heap, (candidate[0] + h(v), candidate[1], next(order), v, candidate[0]))

    if stats is not None:
        stats.update(expanded=len(settled), edge_checks=edge_checks)
    if target not in settled:
        raise nx.NetworkXNoPath(f"No path from {source} to {target}")
    return _rebuild(prev, source, target)


ALGORITHMS = {
    "dijkstra": dijkstra_path,
    "astar": astar_path,
    "networkx": nx.dijkstra_path,
}
