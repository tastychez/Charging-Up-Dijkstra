"""Boston → Dallas in a Tesla: which Superchargers give the shortest trip?

Run from this folder:
    .venv/bin/python main.py               # analysis + figures in figures/
    .venv/bin/python main.py --show        # also play the search live in a window
    .venv/bin/python main.py --range 300   # a different battery range
The first run downloads the map and road data (about a minute); later runs use cache/.
"""

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt

from dijkstra import plan_route
from realmap import road_distances
from stations import END, START, STATIONS
from visualize import (GifWriter, animate_search, plot_range_grid, plot_route,
                       plot_search_snapshots, plot_sweep, plural, short)

COMPARE = [130, 180, 250, 400]  # ranges for the side-by-side figure
SWEEP = range(50, 801)          # ranges for the sensitivity analysis
FIGURES = Path(__file__).parent / "figures"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--range", type=int, default=250,
                        help="miles on a full charge (default 250, a Model 3/Y at highway speed)")
    parser.add_argument("--show", action="store_true", help="play the search live in a window")
    args = parser.parse_args()

    road_miles = road_distances(STATIONS)
    stops, miles, graph, trace = plan_route(road_miles, START, END, args.range)
    if stops is None:
        sys.exit(f"No route with a {args.range}-mile range: some gap is too long. Try a longer range.")

    edges = sum(len(nbrs) for nbrs in graph.values())
    print(f"Charging graph for a {args.range}-mile range: {len(graph)} stations, {edges} directed edges")
    print(f"Driving straight through (no range limit): {road_miles[START][END]} mi\n")

    print("Dijkstra, step by step")
    for step, (u, d, updates) in enumerate(trace, 1):
        improved = ", ".join(f"{short(v)} {nd}" for v, nd in updates)
        print(f"{step:3}. settle {u:<21} {d:>4} mi | {improved or '-'}")

    print(f"\nBest route: {miles} miles, {plural(len(stops) - 2, 'charging stop')}")
    for a, b in zip(stops, stops[1:]):
        print(f"  {a:<21} → {b:<21} {road_miles[a][b]:>4} mi")

    sweep = []
    for r in SWEEP:
        path, total, _, _ = plan_route(road_miles, START, END, r)
        sweep.append((r, total, len(path) - 2 if path else None))

    print("\nVarying the range (only the ranges where the answer changes)")
    last = None
    for r, total, n_stops in sweep:
        if (total, n_stops) != last:
            print(f"  from {r:>3} mi: " + (f"{total} mi, {plural(n_stops, 'stop')}" if total else "no route"))
            last = (total, n_stops)

    print("\nDrawing figures on the real map")
    FIGURES.mkdir(exist_ok=True)
    plot_route(stops, miles, graph, args.range, FIGURES / "route.png")
    plot_range_grid([(r, *plan_route(road_miles, START, END, r)[:3]) for r in COMPARE],
                    FIGURES / "range_comparison.png")
    plot_sweep(sweep, args.range, FIGURES / "range_sweep.png")
    plot_search_snapshots(graph, trace, FIGURES / "search_snapshots.png")
    anim = animate_search(graph, trace, stops, miles, args.range)
    anim.save(FIGURES / "search_on_map.gif", writer=GifWriter(fps=1.5), dpi=100)
    print(f"Figures saved to {FIGURES}")

    if args.show:
        plt.show()


if __name__ == "__main__":
    main()
