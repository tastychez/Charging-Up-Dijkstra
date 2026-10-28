"""Our own Dijkstra on the full charger graph, minimizing total miles.

trip.py picks the route with the fewest charging stops (every leg costs an extra
10,000 miles). Here only the real miles count: the shortest route wins, and among
routes of exactly equal miles, the one with fewer legs.

The search runs on the same graph trip.py builds: every DC fast charger in the
17 states, an edge between two chargers when the leg fits in 80 percent of the
range, plus START and END joined to every charger they can reach.

Usage:
    python shortest_trip.py "Dallas, TX" "Boston, MA"
    python shortest_trip.py "Dallas, TX" "Boston, MA" --range 150
"""

import argparse
import time
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
from matplotlib.collections import LineCollection

import trip
from search import dijkstra_path

FIGURE_DIR = Path(__file__).parent / "figures"


def timed(func, repeat):
    """Run func() `repeat` times; return (last result, fastest seconds)."""
    fastest = float("inf")
    for _ in range(repeat):
        t0 = time.perf_counter()
        result = func()
        fastest = min(fastest, time.perf_counter() - t0)
    return result, fastest


def plot_comparison(shortest, fewest, out_path):
    """Both routes on one map: fewest miles (red) and fewest charging stops (blue)."""
    G, T = shortest["G"], shortest["trip_graph"]
    fig, ax = plt.subplots(figsize=(14, 9))

    lines = [trip._edge_line(G, u, v) for u, v, d in G.edges(data=True)
             if trip._road_type(d) in ("motorway", "trunk")]
    ax.add_collection(LineCollection(lines, colors="#dcdcd8", linewidths=0.5, zorder=1))
    chargers = [n for n in T if n not in ("START", "END")]
    ax.scatter([T.nodes[n]["lon"] for n in chargers], [T.nodes[n]["lat"] for n in chargers],
               s=2, color="#b4b3ad", zorder=2, label=f"Chargers ({len(chargers):,})")

    styles = [(fewest, "#2a78d6", 5.0, "s", "Fewest stops"),
              (shortest, "#d93025", 2.0, "o", "Fewest miles")]
    for result, color, width, marker, label in styles:
        route = result["route"]
        segs = [trip._edge_line(G, u, v) for u, v in zip(route, route[1:])]
        n_stops = len(result["stops"]) - 2
        ax.add_collection(LineCollection(
            segs, colors=color, linewidths=width, alpha=0.9, zorder=3,
            label=f"{label}: {result['total_miles']:,.1f} mi, {n_stops} stops"))
        for i, n in enumerate(result["stops"][1:-1], 1):
            x, y = T.nodes[n]["lon"], T.nodes[n]["lat"]
            ax.scatter(x, y, s=70, marker=marker, color="white", edgecolor=color,
                       linewidth=1.8, zorder=4)

    for label, color in (("START", "#188038"), ("END", "#202124")):
        info = shortest[label.lower()]
        ax.scatter(info["lon"], info["lat"], s=160, marker="*", color=color, zorder=5,
                   label=f"{label.title()}: {info['place']}")

    route_nodes = shortest["route"] + fewest["route"]
    ax.set_aspect(1 / np.cos(np.radians(np.mean([G.nodes[n]["y"] for n in route_nodes]))))
    ax.autoscale()
    ax.set_axis_off()
    ax.set_title(f"{shortest['start']['place']} to {shortest['end']['place']}, "
                 f"{shortest['range_miles']} mile range (legs up to {shortest['usable_miles']:.0f} mi): "
                 "fewest miles vs fewest stops", fontsize=13)
    ax.legend(loc="lower right", frameon=True, fontsize=10)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("start")
    parser.add_argument("end")
    parser.add_argument("--range", type=int, default=250, help="car range in miles")
    parser.add_argument("--region", default="dallas-boston")
    parser.add_argument("--repeat", type=int, default=3, help="timed runs of each search")
    args = parser.parse_args()

    stats = {}
    t0 = time.perf_counter()
    result = trip.plan_trip(args.start, args.end, args.range, args.region,
                            find_path=lambda g, s, t, weight: dijkstra_path(g, s, t, "miles", stats))
    print(f"Loading graphs and planning: {time.perf_counter() - t0:.1f}s")

    T = result["trip_graph"]
    chargers = T.number_of_nodes() - 2
    print(f"\n{result['start']['place']} to {result['end']['place']}, {args.range} mile range "
          f"(legs up to {result['usable_miles']:.0f} miles)")
    print(f"Graph: {chargers:,} chargers + START + END, {T.number_of_edges():,} directed edges")

    print("\nShortest route (fewest miles)")
    for i, leg in enumerate(result["legs"], 1):
        print(f"  Leg {i:2}: {leg['miles']:6.1f} mi  to {leg['to']}")
    print(f"  Total: {result['total_miles']:,.1f} miles, {len(result['stops']) - 2} charging stops")

    ours, ours_s = timed(lambda: dijkstra_path(T, "START", "END", "miles"), args.repeat)
    theirs, nx_s = timed(lambda: nx.dijkstra_path(T, "START", "END", weight="miles"), args.repeat)
    length = lambda path: sum(T[a][b]["miles"] for a, b in zip(path, path[1:]))
    assert abs(length(ours) - length(theirs)) < 1e-6, "our Dijkstra disagrees with NetworkX"

    print("\nSearch (graph already loaded, fastest of "
          f"{args.repeat} run{'s' if args.repeat > 1 else ''})")
    print(f"  Our Dijkstra:      {ours_s:7.3f}s   expanded {stats['expanded']:,} of "
          f"{T.number_of_nodes():,} nodes, checked {stats['edge_checks']:,} edges")
    print(f"  NetworkX Dijkstra: {nx_s:7.3f}s   same length: {length(theirs):,.1f} miles")

    # trip.py's objective (fewest stops, then fewest miles), searched with our Dijkstra.
    fewest = trip.plan_trip(args.start, args.end, args.range, args.region,
                            find_path=lambda g, s, t, weight: dijkstra_path(g, s, t, "cost"))
    print("\nFewest-stops route (trip.py's objective)")
    for i, leg in enumerate(fewest["legs"], 1):
        print(f"  Leg {i:2}: {leg['miles']:6.1f} mi  to {leg['to']}")
    print(f"  Total: {fewest['total_miles']:,.1f} miles, {len(fewest['stops']) - 2} charging stops")

    FIGURE_DIR.mkdir(exist_ok=True)
    slug = lambda s: s.split(",")[0].lower().replace(" ", "-")
    out = FIGURE_DIR / f"shortest_{slug(args.start)}_{slug(args.end)}_{args.range}mi.png"
    trip.plot_trip(result, out)
    both = FIGURE_DIR / f"compare_{slug(args.start)}_{slug(args.end)}_{args.range}mi.png"
    plot_comparison(result, fewest, both)
    print(f"\nSaved {out}\nSaved {both}")


if __name__ == "__main__":
    main()
