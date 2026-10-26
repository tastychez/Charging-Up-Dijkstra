"""Compare our Dijkstra, our A* and NetworkX's Dijkstra on the full trip graph.

For each range, every algorithm searches the same graph for the fewest miles. The script checks that they agree on the
best weight and reports how many vertices each one expanded and how long it took.

Usage:
    python compare_algorithms.py "Dallas, TX" "Boston, MA"
    python compare_algorithms.py "Dallas, TX" "Boston, MA" --ranges 150 250 300
"""

import argparse
import time

import networkx as nx

import search
import trip

GOALS = {"miles": "fewest miles"}


def fastest(func, repeat):
    best = float("inf")
    for _ in range(repeat):
        t0 = time.perf_counter()
        result = func()
        best = min(best, time.perf_counter() - t0)
    return result, best


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("start")
    parser.add_argument("end")
    parser.add_argument("--ranges", type=int, nargs="+", default=[150, 250, 300])
    parser.add_argument("--region", default="dallas-boston")
    parser.add_argument("--repeat", type=int, default=3, help="timed runs per search")
    args = parser.parse_args()

    rows = []
    for range_miles in args.ranges:
        T = trip.plan_trip(args.start, args.end, range_miles, args.region)["trip_graph"]
        print(f"{range_miles} mi range: {T.number_of_nodes():,} vertices, {T.number_of_edges():,} edges")
        for weight, goal in GOALS.items():
            length = lambda path: sum(T[a][b][weight] for a, b in zip(path, path[1:]))
            miles = lambda path: sum(T[a][b]["miles"] for a, b in zip(path, path[1:]))
            nx_path, nx_s = fastest(lambda: nx.dijkstra_path(T, "START", "END", weight=weight), args.repeat)
            for name, func in (("our Dijkstra", search.dijkstra_path), ("our A*", search.astar_path)):
                stats = {}
                path, secs = fastest(lambda: func(T, "START", "END", weight, stats=stats), args.repeat)
                assert abs(length(path) - length(nx_path)) < 1e-6, f"{name} disagrees with NetworkX"
                rows.append((range_miles, goal, name, miles(path), len(path) - 2,
                             stats["expanded"], stats["edge_checks"], secs))
            rows.append((range_miles, goal, "NetworkX Dijkstra", miles(nx_path), len(nx_path) - 2,
                         None, None, nx_s))

    print(f"\n{'range':>5}  {'goal':<13} {'algorithm':<18} {'miles':>8} {'stops':>5} "
          f"{'expanded':>9} {'edges checked':>13} {'time':>8}")
    count = lambda n: "-" if n is None else f"{n:,}"   # NetworkX doesn't report its work
    for r, goal, name, mi, stops, expanded, checks, secs in rows:
        print(f"{r:>5}  {goal:<13} {name:<18} {mi:>8,.1f} {stops:>5} "
              f"{count(expanded):>9} {count(checks):>13} {secs * 1000:>5.0f} ms")
    print("\nAll three algorithms found routes of the same best weight in every case.")


if __name__ == "__main__":
    main()
