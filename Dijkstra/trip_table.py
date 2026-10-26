"""Search work and time of Dijkstra on two real trips, as a slide table.

Trips: Boston → Dallas and Buffalo, NY → Springfield, MO, on the same real network
(network.py) with a 200-mile range (80% of a 250-mile Model Y). Boston → Dallas runs
our hand-written Dijkstra, NetworkX and SciPy; Buffalo → Springfield only ours.

  Nodes expanded  vertices taken off the heap with their distance final
  Edges checked   edges looked at while relaxing those vertices
  Median time     median of --trials timed searches; building the graph is not timed

Run from this folder:
    ../.venv/bin/python trip_table.py              # 101 timed runs per search
    ../.venv/bin/python trip_table.py --trials 21
The first run builds each trip's network (about a minute each) and caches it in cache/.
"""

import argparse
import statistics
import time

import networkx as nx
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra as scipy_dijkstra

from dijkstra import charging_graph, dijkstra, shortest_path
from network import END, START, load_network

RANGE = 200
TRIPS = [(START, END), ("Buffalo, NY", "Springfield, MO")]


def median_ms(func, trials):
    func()  # untimed warm-up
    times = []
    for _ in range(trials):
        t0 = time.perf_counter()
        func()
        times.append((time.perf_counter() - t0) * 1000)
    return statistics.median(times)


def run_hand(graph, start, end, trials):
    best, prev, trace = dijkstra(graph, start, end)
    path = shortest_path(prev, start, end)
    checked = sum(len(graph[u]) for u, _, _ in trace if u != end)  # the end is not relaxed
    ms = median_ms(lambda: dijkstra(graph, start, end), trials)
    return best[end], path, len(trace), checked, ms


def run_networkx(graph, start, end, trials):
    G = nx.DiGraph()
    G.add_weighted_edges_from((a, b, w) for a, nbrs in graph.items() for b, w in nbrs.items())

    # Count the work in one extra run: NetworkX calls the weight function once per
    # edge it checks, from every vertex it expands except the end.
    relaxed, checked = set(), 0
    def counting_weight(u, v, d):
        nonlocal checked
        relaxed.add(u)
        checked += 1
        return d["weight"]
    miles, path = nx.single_source_dijkstra(G, start, end, weight=counting_weight)

    ms = median_ms(lambda: nx.single_source_dijkstra(G, start, end), trials)
    return miles, path, len(relaxed) + 1, checked, ms


def run_scipy(graph, start, end, trials):
    vertices = list(graph)
    index = {v: i for i, v in enumerate(vertices)}
    rows, cols, miles = [], [], []
    for a, nbrs in graph.items():
        for b, w in nbrs.items():
            rows.append(index[a])
            cols.append(index[b])
            miles.append(w)
    matrix = csr_matrix((miles, (rows, cols)), shape=(len(vertices),) * 2)
    search = lambda: scipy_dijkstra(matrix, directed=True, indices=index[start], return_predecessors=True)
    dist, pred = search()

    path, i = [], index[end]
    while i >= 0:            # SciPy marks "no predecessor" with -9999
        path.append(vertices[i])
        i = pred[i]
    # SciPy does not stop at the end: it settles every reachable vertex.
    reached = np.isfinite(dist)
    checked = int(np.diff(matrix.indptr)[reached].sum())
    return float(dist[index[end]]), path[::-1], int(reached.sum()), checked, median_ms(search, trials)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=101, help="timed runs per search (default 101)")
    args = parser.parse_args()

    rows = []
    for start, end in TRIPS:
        _, _, _, legs = load_network(start, end)
        graph = charging_graph(legs, RANGE)
        edges = sum(map(len, graph.values()))
        print(f"{start} → {end}: {len(graph):,} vertices, {edges:,} edges", flush=True)
        methods = {"Hand-written": run_hand}
        if (start, end) == TRIPS[0]:
            methods.update({"NetworkX": run_networkx, "SciPy": run_scipy})
        answers = []
        for name, run in methods.items():
            miles, path, expanded, checked, ms = run(graph, start, end, args.trials)
            answers.append((miles, path))
            rows.append((f"{start.split(',')[0]} → {end.split(',')[0]}", name, ms, expanded, checked,
                         miles, len(path) - 2))
        assert all(abs(m - answers[0][0]) < 1e-6 for m, _ in answers), f"methods disagree: {answers}"

    print(f"\n{RANGE}-mile range, median of {args.trials} runs\n")
    print("| Trip | Dijkstra | Median time (ms) | Nodes expanded | Edges checked | Miles | Stops |")
    print("|---|---|---|---|---|---|---|")
    for trip, name, ms, expanded, checked, miles, stops in rows:
        print(f"| {trip} | {name} | {ms:,.2f} | {expanded:,} | {checked:,} | {miles:,.2f} | {stops} |")


if __name__ == "__main__":
    main()
