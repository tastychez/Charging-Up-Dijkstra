"""Our hand-written Dijkstra (dijkstra.py) against two library versions, on the real network:

  NetworkX  networkx.single_source_dijkstra, pure Python (what trip.py used at first)
  SciPy     scipy.sparse.csgraph.dijkstra, compiled C (what charger_graph.py uses)

For each range, all three search the same charging graph from Boston to Dallas. The
script checks they find the same shortest distance, then draws each one's route and
compares their running times. Only the search is timed, not building the graph.

Run from this folder:
    ../.venv/bin/python compare_library.py
Saves figures/library_routes.png and figures/library_runtime.png.
"""

import time
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra as scipy_dijkstra

from dijkstra import charging_graph, dijkstra, shortest_path
from network import END, MAX_RANGE, START, load_network
from visualize import BG, GRID, INK, MUTED, draw_map, draw_route, finish, plural

RANGES = list(range(40, MAX_RANGE + 1, 20))   # 40, 60, ..., 240
CHOSEN = 200                                  # range for the route maps
REPEAT = 3                                    # timed runs per search; the fastest counts
FIGURES = Path(__file__).parent / "figures"

# Categorical slots 1-3 of the validated palette (blue, orange, aqua), in fixed order.
METHODS = {"Hand-written": "#2a78d6", "NetworkX": "#eb6834", "SciPy": "#1baf7a"}


def fastest(func):
    best, result = float("inf"), None
    for _ in range(REPEAT):
        t0 = time.perf_counter()
        result = func()
        best = min(best, time.perf_counter() - t0)
    return result, best


def run_hand(graph):
    (dist, prev, _), secs = fastest(lambda: dijkstra(graph, START, END))
    return shortest_path(prev, START, END), dist.get(END), secs


def run_networkx(graph):
    G = nx.DiGraph()
    G.add_weighted_edges_from((a, b, w) for a, nbrs in graph.items() for b, w in nbrs.items())
    def search():
        try:
            return nx.single_source_dijkstra(G, START, END)
        except nx.NetworkXNoPath:
            return None, None
    (length, path), secs = fastest(search)
    return path, length, secs


def run_scipy(graph, vertices, index):
    rows, cols, miles = [], [], []
    for a, nbrs in graph.items():
        for b, w in nbrs.items():
            rows.append(index[a])
            cols.append(index[b])
            miles.append(w)
    matrix = csr_matrix((miles, (rows, cols)), shape=(len(vertices), len(vertices)))
    (dist, pred), secs = fastest(lambda: scipy_dijkstra(matrix, directed=True, indices=index[START],
                                                        return_predecessors=True))
    if not np.isfinite(dist[index[END]]):
        return None, None, secs
    path, i = [], index[END]
    while i >= 0:            # SciPy marks "no predecessor" with -9999
        path.append(vertices[i])
        i = pred[i]
    return path[::-1], float(dist[index[END]]), secs


def plot_routes(results, graph, path):
    """One map per method: the route it found at the chosen range."""
    fig, axes = plt.subplots(1, 3, figsize=(21, 5.6))
    for ax, (name, (stops, miles, secs)) in zip(axes, results.items()):
        draw_map(ax)
        draw_route(ax, stops, lw=2.2, color=METHODS[name])
        finish(ax, f"{name} Dijkstra", f"{miles:,.1f} mi · {plural(len(stops) - 2, 'stop')} · "
               f"search took {secs * 1000:,.0f} ms", size=12)
    fig.suptitle(f"Same graph, same answer: {CHOSEN}-mile range, "
                 f"{len(graph) - 2:,} chargers, {sum(map(len, graph.values())):,} edges",
                 x=0.01, ha="left", fontweight="bold", fontsize=13)
    fig.tight_layout()
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def plot_runtime(table, path):
    """Search time against the number of edges, one line per method (log scale)."""
    fig, ax = plt.subplots(figsize=(10, 5.6))
    for name, color in METHODS.items():
        edges = [row["edges"] / 1e6 for row in table]
        ms = [row[name] * 1000 for row in table]
        ax.plot(edges, ms, color=color, lw=2, marker="o", ms=8, mec=BG, mew=2, label=name)
        ax.annotate(f"{name}  {ms[-1]:,.0f} ms", (edges[-1], ms[-1]), xytext=(10, 0),
                    textcoords="offset points", va="center", fontsize=10, color=INK)
    ax.set_yscale("log")
    ax.set_xlabel("Edges in the charging graph (millions); the range grows from "
                  f"{table[0]['range']} to {table[-1]['range']} miles")
    ax.set_ylabel("Search time (ms, log scale)")
    ax.grid(color=GRID, lw=0.6)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_xlim(right=max(row["edges"] for row in table) / 1e6 * 1.22)
    ax.legend(loc="upper left", frameon=False)
    ax.set_title("Boston → Dallas: how long each Dijkstra takes", loc="left", pad=24)
    ax.text(0, 1.015, "All three find the same shortest distance at every range. SciPy runs "
            "compiled C and finds every distance; the other two are pure Python and stop at Dallas.",
            transform=ax.transAxes, color=MUTED, fontsize=9, va="bottom")
    fig.tight_layout()
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def main():
    _, _, _, legs = load_network()
    vertices = list(legs)
    index = {v: i for i, v in enumerate(vertices)}

    print(f"{'range':>5} {'edges':>10} | {'miles':>8} {'stops':>5} | "
          + " ".join(f"{name:>12}" for name in METHODS) + " | same miles, same stops")
    table, routes = [], {}
    for r in RANGES:
        graph = charging_graph(legs, r)
        runs = {"Hand-written": run_hand(graph), "NetworkX": run_networkx(graph),
                "SciPy": run_scipy(graph, vertices, index)}
        lengths = [miles for _, miles, _ in runs.values()]
        same = (all(m is None for m in lengths)
                or all(m is not None and abs(m - lengths[0]) < 1e-6 for m in lengths))
        assert same, f"the methods disagree at {r} miles: {lengths}"
        stops, miles, _ = runs["Hand-written"]
        same_stops = all(path == stops for path, _, _ in runs.values())
        row = {"range": r, "edges": sum(map(len, graph.values()))}
        row.update({name: secs for name, (_, _, secs) in runs.items()})
        table.append(row)
        if r == CHOSEN:
            routes = runs
            chosen_graph = graph
        print(f"{r:>5} {row['edges']:>10,} | "
              + (f"{miles:>8,.1f} {len(stops) - 2:>5}" if stops else f"{'no route':>8} {'-':>5}")
              + " | " + " ".join(f"{row[name] * 1000:>9,.1f} ms" for name in METHODS)
              + f" | yes, {'yes' if same_stops else 'no (a tie: different stops, same miles)'}")

    FIGURES.mkdir(exist_ok=True)
    plot_routes(routes, chosen_graph, FIGURES / "library_routes.png")
    plot_runtime(table, FIGURES / "library_runtime.png")
    print(f"\nSaved {FIGURES / 'library_routes.png'} and {FIGURES / 'library_runtime.png'}")


if __name__ == "__main__":
    main()
