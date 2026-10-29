"""Dijkstra against A* with two heuristics, on the same two trips as trip_table.py.

  Dijkstra              our hand-written dijkstra.py
  A* Haversine          A* guided by the straight-line (great-circle) miles to the end
  A* Scaled Manhattan   A* guided by north-south + east-west miles to the end, scaled down

A* only finds the shortest route if its guess never overestimates. Manhattan miles can
overestimate a leg, so, as on the david-astar branch, every guess is multiplied by the
largest scale <= 1 that keeps h[u] <= miles(u, v) + h[v] on every edge. The scaling is
done once before timing; only the searches are timed (median of --trials runs).

Run from this folder:
    ../.venv/bin/python astar_table.py
"""

import argparse
import heapq
from math import asin, cos, radians, sin, sqrt

from dijkstra import charging_graph, dijkstra, shortest_path
from network import load_network
from trip_table import RANGE, TRIPS, median_ms

EARTH_MILES = 3958.7


def haversine_miles(a, b):
    lat1, lon1, lat2, lon2 = map(radians, (*a, *b))
    x = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_MILES * asin(sqrt(x))


def manhattan_miles(a, b):
    lat1, lon1, lat2, lon2 = map(radians, (*a, *b))
    return EARTH_MILES * (abs(lat2 - lat1) + abs(cos(lat2) * (lon2 - lon1)))


def scaled_guess(graph, coords, end, miles_to):
    """h[v] for every vertex, scaled so it never drops by more than an edge's miles."""
    raw = {v: miles_to(coords[v], coords[end]) for v in graph}
    scale = 1.0
    for u, nbrs in graph.items():
        for v, w in nbrs.items():
            if raw[u] - raw[v] > w:
                scale = min(scale, w / (raw[u] - raw[v]))
    return {v: h * scale for v, h in raw.items()}, scale


def astar(graph, source, target, h):
    best = {source: 0}
    prev = {}
    heap = [(h[source], 0, source)]  # (miles so far + guess to the end, miles so far, node)
    expanded = 0
    while heap:
        _, miles, u = heapq.heappop(heap)
        if miles > best[u]:
            continue  # outdated entry
        expanded += 1
        if u == target:
            break
        for v, w in graph[u].items():
            new_miles = miles + w
            if v not in best or new_miles < best[v]:
                best[v] = new_miles
                prev[v] = u
                heapq.heappush(heap, (new_miles + h[v], new_miles, v))
    return best, prev, expanded


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=101, help="timed runs per search (default 101)")
    args = parser.parse_args()

    rows = []
    for start, end in TRIPS:
        coords, _, _, legs = load_network(start, end)
        graph = charging_graph(legs, RANGE)
        trip = f"{start.split(',')[0]} → {end.split(',')[0]}"

        best, prev, trace = dijkstra(graph, start, end)
        route = shortest_path(prev, start, end)
        ms = median_ms(lambda: dijkstra(graph, start, end), args.trials)
        rows.append((trip, "Dijkstra", len(trace), ms, best[end], len(route) - 2))

        for name, miles_to in (("A* Haversine", haversine_miles), ("A* Scaled Manhattan", manhattan_miles)):
            h, scale = scaled_guess(graph, coords, end, miles_to)
            a_best, a_prev, expanded = astar(graph, start, end, h)
            assert abs(a_best[end] - best[end]) < 1e-6, f"{name} found {a_best[end]}, Dijkstra {best[end]}"
            a_route = shortest_path(a_prev, start, end)
            ms = median_ms(lambda: astar(graph, start, end, h), args.trials)
            rows.append((trip, name, expanded, ms, a_best[end], len(a_route) - 2))
            print(f"{trip}: {name} scale {scale:.4f}", flush=True)

        print(f"{trip}: {best[end]:,.2f} mi, {len(route) - 2} stops for all three", flush=True)

    print(f"\n{RANGE}-mile range, median of {args.trials} runs\n")
    print("| Trip | Algorithm | Expanded | Fewer than Dijkstra | Time |")
    print("|---|---|---|---|---|")
    base = {}
    for trip, name, expanded, ms, _, _ in rows:
        fewer = "–" if name == "Dijkstra" else f"{1 - expanded / base[trip]:.0%}"
        base.setdefault(trip, expanded)
        print(f"| {trip} | {name} | {expanded:,} | {fewer} | {ms:,.0f} ms |")


if __name__ == "__main__":
    main()
