"""Dijkstra's algorithm, and the range-limited charging graph it runs on."""

import heapq


def dijkstra(graph, source, target=None):
    """Shortest paths from `source` in a graph {node: {neighbor: miles}}.

    Stops as soon as `target` is settled (or explores everything if target is None).
    Among routes of equal length, the one with fewer edges (charging stops) wins.

    Returns (dist, prev, trace):
      dist  - shortest distance to every reached node
      prev  - the node we came from on that shortest path
      trace - one entry per settled node, in settling order:
              (node, distance, [(neighbor, its new distance), ...])
    """
    best = {source: (0, 0)}          # node -> (miles, edges) of best known route
    prev = {}
    settled = set()
    trace = []
    heap = [(0, 0, source)]

    while heap:
        miles, edges, u = heapq.heappop(heap)
        if u in settled:
            continue                 # outdated heap entry
        settled.add(u)

        updates = []
        if u != target:
            for v, w in graph[u].items():
                candidate = (miles + w, edges + 1)
                if v not in settled and (v not in best or candidate < best[v]):
                    best[v] = candidate
                    prev[v] = u
                    heapq.heappush(heap, (*candidate, v))
                    updates.append((v, candidate[0]))
        trace.append((u, miles, updates))

        if u == target:
            break

    dist = {node: miles for node, (miles, _) in best.items()}
    return dist, prev, trace


def shortest_path(prev, source, target):
    """Trace back from `target` to `source`. Returns None if target was never reached."""
    if target != source and target not in prev:
        return None
    path = [target]
    while path[-1] != source:
        path.append(prev[path[-1]])
    return path[::-1]


def charging_graph(road_miles, max_range):
    """Edge A → B only if a fully charged car can drive the road from A to B.

    Edge weight = road distance. The battery limit lives in which edges exist.
    The graph is directed because A → B and B → A can differ by a few miles.
    """
    return {a: {b: d for b, d in row.items() if b != a and d <= max_range}
            for a, row in road_miles.items()}


def plan_route(road_miles, source, target, max_range):
    """Best charging route for one range. Returns (stops, total_miles, graph, trace).

    stops is None (and total_miles is None) when the trip is impossible.
    """
    graph = charging_graph(road_miles, max_range)
    dist, prev, trace = dijkstra(graph, source, target)
    return shortest_path(prev, source, target), dist.get(target), graph, trace
