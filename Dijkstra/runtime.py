"""A minimal Dijkstra, and a stopwatch to see how its running time grows.

Run from this folder:
    ../.venv/bin/python runtime.py
Prints the Boston → Dallas route on the real network, a timing table, and saves
figures/runtime.png.
"""

import heapq
import math
import random
import time
from pathlib import Path

import matplotlib.pyplot as plt

import dijkstra as full
from network import END, START, load_network

FIGURES = Path(__file__).parent / "figures"
SIZES = [1000, 2000, 4000, 8000, 16000, 32000, 64000]  # nodes in the random test graphs
DEGREE = 5                                               # roads leaving each node


def dijkstra(graph, source, target=None):
    """Shortest distances from `source` in a graph {node: {neighbor: miles}}.

    Returns (best, prev). If `target` is given the search stops once it is settled,
    so only best[target] (and the nodes settled before it) are guaranteed final.
    """
    best = {source: 0}   # starting point is zero
    prev = {}            # the node we came from on the best route
    done = set()         # nodes whose distance is final
    heap = [(0, source)] # waitlist

    # the distance from starting point to u is miles.
    # u is current position, v is the neighbour to u, and w is the distance from u to v
    while heap:
        miles, u = heapq.heappop(heap) # take the closest point
        if u in done:
            continue                   # an older, longer entry for u
        done.add(u)
        if u == target:
            break                      # nothing left in the heap can beat this
        for v, w in graph[u].items():
            new_miles = miles + w
            if v not in best or new_miles < best[v]:
                best[v] = new_miles
                prev[v] = u
                heapq.heappush(heap, (new_miles, v))

    return best, prev


def path_to(prev, source, target):
    """Walk prev back from `target` to `source`. None if target was never reached."""
    if target != source and target not in prev:
        return None
    path = [target]
    while path[-1] != source:
        path.append(prev[path[-1]])
    return path[::-1]


def runtime(func, *args, repeat=5):
    """Call func(*args) `repeat` times. Returns (result, fastest time in seconds).

    The fastest run is the one least disturbed by whatever else the computer was doing.
    """
    fastest = math.inf
    for _ in range(repeat):
        start = time.perf_counter()
        result = func(*args)
        fastest = min(fastest, time.perf_counter() - start)
    return result, fastest


def random_graph(n, degree, seed=0):
    """n nodes, each with `degree` roads of 1-100 miles to random nodes.

    A road i → i+1 is always included so every node is reachable from node 0.
    """
    rng = random.Random(seed)
    graph = {}
    for u in range(n):
        roads = {(u + 1) % n: rng.randint(1, 100)}
        while len(roads) < degree:
            v = rng.randrange(n)
            if v != u:
                roads[v] = rng.randint(1, 100)
        graph[u] = roads
    return graph


def demo_real_trip(max_range=200):
    _, cities, _, legs = load_network()
    graph = full.charging_graph(legs, max_range)
    (best, prev), seconds = runtime(dijkstra, graph, START, END, repeat=3)

    stops = path_to(prev, START, END)
    print(f"Boston → Dallas with a {max_range}-mile range "
          f"({len(graph) - 2:,} chargers, {sum(map(len, graph.values())):,} edges)")
    print(f"  {best[END]:,.1f} miles, {len(stops) - 2} stops: " + " → ".join(cities[v] for v in stops))
    print(f"  runtime: {seconds * 1e3:.0f} ms")

    expected = full.plan_route(legs, START, END, max_range)[1]
    assert abs(best[END] - expected) < 1e-6, f"simple version says {best[END]}, dijkstra.py says {expected}"
    print(f"  matches dijkstra.py ({expected:,.1f} miles)\n")


def demo_growth():
    """Time Dijkstra on bigger and bigger graphs and compare with (V + E) log V."""
    print("Runtime on random graphs (whole graph explored from node 0)")
    print(f"{'V':>7} {'E':>8} {'time (ms)':>10} {'ns per (V+E)·log2 V':>21}")
    rows = []
    for n in SIZES:
        graph = random_graph(n, DEGREE)
        e = n * DEGREE
        (best, _), seconds = runtime(dijkstra, graph, 0, repeat=3)
        assert len(best) == n
        work = (n + e) * math.log2(n)
        rows.append((n, e, seconds, work))
        print(f"{n:>7} {e:>8} {seconds * 1e3:>10.1f} {seconds / work * 1e9:>21.1f}")
    print("If the last column stayed flat, time would grow exactly like (V + E) log V.\n")
    return rows


def plot_growth(rows, path):
    sizes = [n for n, _, _, _ in rows]
    ms = [s * 1e3 for _, _, s, _ in rows]
    # Scale the theory curve to pass through the smallest measurement.
    scale = ms[0] / rows[0][3]
    theory = [work * scale for _, _, _, work in rows]

    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.plot(sizes, theory, color="#9a9994", linewidth=2, linestyle="--",
            label="(V + E) log V, scaled")
    ax.plot(sizes, ms, color="#2a78d6", linewidth=2, marker="o", markersize=7,
            markeredgecolor="white", markeredgewidth=2, label="measured")
    ax.annotate(f"{ms[-1]:.0f} ms", (sizes[-1], ms[-1]), textcoords="offset points",
                xytext=(-8, 8), ha="right", color="#0b0b0b")

    ax.set_title(f"Dijkstra runtime on random graphs ({DEGREE} roads per node)",
                 loc="left", color="#0b0b0b")
    ax.set_xscale("log", base=2)
    ax.set_yscale("log")
    ax.set_xticks(sizes, [f"{n // 1000}k" for n in sizes])
    ax.set_xlabel("nodes V (log scale)", color="#52514e")
    ax.set_ylabel("time (ms, log scale)", color="#52514e")
    ax.grid(color="#e4e3df", linewidth=0.8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.tick_params(colors="#52514e")
    ax.legend(frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    demo_real_trip()
    rows = demo_growth()
    FIGURES.mkdir(exist_ok=True)
    plot_growth(rows, FIGURES / "runtime.png")
    print(f"Chart saved to {FIGURES / 'runtime.png'}")


if __name__ == "__main__":
    main()
