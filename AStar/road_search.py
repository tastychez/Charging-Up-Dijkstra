"""Our own heap search for road mileage; no library shortest-path calls.

This is the same best-distance/heap idea as A* with h=0. It prepares road
distances, while astar.py chooses the charging-stop route with either heuristic.
"""

import hashlib
from heapq import heappop, heappush
from math import isfinite


class RoadNetwork:
    """Keep the shortest parallel road, preserving one-way directions."""

    def __init__(self, graph):
        self.nodes = list(graph.nodes)
        self.index = {node: i for i, node in enumerate(self.nodes)}
        self.outgoing = [[] for _ in self.nodes]
        self.incoming = [[] for _ in self.nodes]
        digest = hashlib.sha256()
        multiple = graph.is_multigraph()
        for first in self.nodes:
            row = self.index[first]
            attributes = graph.nodes[first]
            digest.update(repr((first, attributes.get("x"), attributes.get("y"))).encode())
            for second, edge in graph[first].items():
                roads = edge.values() if multiple else (edge,)
                miles = min(float(road["miles"]) for road in roads)
                if not isfinite(miles) or miles < 0:
                    raise ValueError("Road distances must be finite and nonnegative.")
                column = self.index[second]
                self.outgoing[row].append((column, miles))
                self.incoming[column].append((row, miles))
                digest.update(repr((row, column, miles)).encode())
        self.signature = digest.hexdigest()

    def _search(self, source, cutoff, targets=None, reverse=False, destination=None):
        """Bounded, nonnegative-weight heap search over integer road indices."""
        if cutoff < 0:
            return {}, {}
        adjacency = self.incoming if reverse else self.outgoing
        best, previous, reached = {source: 0.0}, {}, {}
        frontier = [(0.0, source)]
        while frontier:
            miles, current = heappop(frontier)
            if miles != best[current]:
                continue
            if targets is None or current in targets:
                reached[current] = miles
            if current == destination or (targets is not None and len(reached) == len(targets)):
                break
            for neighbor, edge_miles in adjacency[current]:
                candidate = miles + edge_miles
                if candidate <= cutoff and candidate < best.get(neighbor, float("inf")):
                    best[neighbor] = candidate
                    if destination is not None:
                        previous[neighbor] = current
                    heappush(frontier, (candidate, neighbor))
        return reached, previous

    def reachable(self, source, cutoff, targets=None, reverse=False):
        return self._search(source, cutoff, targets=targets, reverse=reverse)[0]

    def path(self, source, destination, cutoff=float("inf")):
        distances, previous = self._search(source, cutoff, destination=destination)
        if destination not in distances:
            return None
        route = [destination]
        while route[-1] != source:
            route.append(previous[route[-1]])
        route.reverse()
        return [self.nodes[i] for i in route], distances[destination]
