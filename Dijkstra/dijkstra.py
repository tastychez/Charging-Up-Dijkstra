"""Dijkstra's algorithm, and the range-limited charging graph it runs on."""

import heapq
from bisect import bisect_right


def dijkstra(graph, source, target=None):
    """Shortest distances from `source` in a graph {node: {neighbor: miles}}.

    Returns (best, prev, trace): the distance to every reached node, the node we came
    from on that route, and one (node, miles, [(neighbor, new miles), ...]) entry per
    settled node, in settling order, for the animation.
    """
    best = {source: 0} # starting point is zero
    prev = {} # where we came from
    heap = [(0, source)] # waitlist
    trace = [] # settled points in order


    # the distance from starting point to u is miles.
    # u is current position, v is the neighbour to u, and w is the distance from u to v
    while heap:
        miles, u = heapq.heappop(heap) # take the closest point
        if miles > best[u]:
            continue # outdated entry, a shorter way to u was already found
        updates = []
        if u != target:
            for v, w in graph[u].items():
                new_miles = miles + w
                if v not in best or new_miles < best[v]:
                    best[v] = new_miles
                    prev[v] = u
                    heapq.heappush(heap, (new_miles, v))
                    updates.append((v, new_miles))
        trace.append((u, miles, updates))
        if u == target:
            break # the target's distance is final

    return best, prev, trace


def shortest_path(prev, source, target):
    """Trace back from `target` to `source`. Returns None if target was never reached."""
    if target != source and target not in prev:
        return None
    path = [target]
    while path[-1] != source:
        path.append(prev[path[-1]])
    return path[::-1]


def charging_graph(legs, max_range):
    """Edge A → B only if the car can drive the leg from A to B on one charge:
    leg miles <= max_range (80 percent of a full battery, e.g. 200 for a 250-mile car).

    Edge weight = leg miles. The battery limit lives in which edges exist.
    The graph is directed because A → B and B → A can differ by a few miles.
    legs[a] = (miles, neighbors), shortest first (see network.load_network).
    """
    graph = {}
    for a, (miles, nbrs) in legs.items():
        k = bisect_right(miles, max_range)
        graph[a] = dict(zip(nbrs[:k], miles[:k]))
    return graph


def plan_route(legs, source, target, max_range):
    """Best charging route for one range. Returns (stops, total_miles, graph, trace).

    stops is None (and total_miles is None) when the trip is impossible.
    """
    graph = charging_graph(legs, max_range)
    dist, prev, trace = dijkstra(graph, source, target)
    return shortest_path(prev, source, target), dist.get(target), graph, trace
