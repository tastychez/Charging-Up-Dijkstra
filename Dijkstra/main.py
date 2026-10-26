"""Boston → Dallas in an EV: which DC fast chargers give the shortest trip?

Runs on the real network: every public DC fast charger in the 17 states between
Boston and Dallas (see network.py). Needs the root .venv and data/ (root README).

Run from this folder:
    ../.venv/bin/python main.py               # analysis + figures in figures/
    ../.venv/bin/python main.py --show        # also play the search live in a window
    ../.venv/bin/python main.py --range 240   # a different range (up to 240)
The first run loads the full network (about 15 seconds) and caches it in cache/.
"""

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt

from dijkstra import plan_route
from network import END, MAX_RANGE, START, load_network
from visualize import (GifWriter, animate_search, plot_range_grid, plot_route,
                       plot_search_snapshots, plot_sweep, plural, short)

COMPARE = [120, 160, 200, 240]   # ranges for the side-by-side figure
SWEEP = range(40, MAX_RANGE + 1, 4)  # ranges for the sensitivity analysis
PRINT_EVERY = 500                # print one line per this many Dijkstra steps
FIGURES = Path(__file__).parent / "figures"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--range", type=int, default=200,
                        help=f"longest leg in miles: 80%% of a full charge (default 200 = 80%% "
                             f"of a 250-mile Model Y, up to {MAX_RANGE})")
    parser.add_argument("--show", action="store_true", help="play the search live in a window")
    args = parser.parse_args()
    if not 0 < args.range <= MAX_RANGE:
        sys.exit(f"--range must be between 1 and {MAX_RANGE}: data/ only has legs up to "
                 f"{MAX_RANGE} miles.")

    _, _, names, legs = load_network()
    stops, miles, graph, trace = plan_route(legs, START, END, args.range)
    if stops is None:
        sys.exit(f"No route with a {args.range}-mile range: some gap is too long. Try a longer range.")

    edges = sum(len(nbrs) for nbrs in graph.values())
    print(f"Charging graph for a {args.range}-mile range: "
          f"{len(graph) - 2:,} chargers + {short(START)} + {short(END)}, {edges:,} directed edges\n")

    print(f"Dijkstra, every {PRINT_EVERY}th step")
    for step, (u, d, updates) in enumerate(trace, 1):
        if step % PRINT_EVERY == 0 or step in (1, len(trace)):
            print(f"{step:6,}. settle {short(u):<26} {d:8,.1f} mi | improved {len(updates):,} neighbors")
    print(f"Settled {len(trace):,} of {len(graph):,} vertices before {short(END)}")

    print(f"\nBest route: {miles:,.1f} miles, {plural(len(stops) - 2, 'charging stop')}")
    for a, b in zip(stops, stops[1:]):
        print(f"  {short(a):<26} → {short(b):<26} {graph[a][b]:6.1f} mi   {names[b]}")

    sweep = []
    for r in SWEEP:
        path, total, _, _ = plan_route(legs, START, END, r)
        sweep.append((r, total, len(path) - 2 if path else None))

    print("\nVarying the range (only the ranges where the answer changes)")
    last = None
    for r, total, n_stops in sweep:
        if (total, n_stops) != last:
            print(f"  from {r:>3} mi: " + (f"{total:,.1f} mi, {plural(n_stops, 'stop')}" if total else "no route"))
            last = (total, n_stops)

    print("\nDrawing figures on the real map")
    FIGURES.mkdir(exist_ok=True)
    plot_route(stops, miles, graph, args.range, FIGURES / "route.png")
    plot_range_grid([(r, *plan_route(legs, START, END, r)[:3]) for r in COMPARE],
                    FIGURES / "range_comparison.png")
    plot_sweep(sweep, args.range, FIGURES / "range_sweep.png")
    plot_search_snapshots(trace, FIGURES / "search_snapshots.png")
    anim = animate_search(graph, trace, stops, miles, args.range)
    anim.save(FIGURES / "search_on_map.gif", writer=GifWriter(fps=1.5), dpi=90)
    print(f"Figures saved to {FIGURES}")

    if args.show:
        plt.show()


if __name__ == "__main__":
    main()
