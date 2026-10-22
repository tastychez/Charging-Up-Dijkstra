"""Plot the road network with EV chargers on top.

Usage:
    python visualize.py
    python visualize.py --region rhode-island --states RI
    python visualize.py --region boston --roads all
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import osmnx as ox

from data import ALL_ROADS, CITIES, MAJOR_ROADS, load_chargers, load_street_graph, snap_chargers

FIGURE_DIR = Path(__file__).parent / "figures"


def plot_network(G, chargers, title, out_path):
    fig, ax = ox.plot_graph(
        G, show=False, close=False, bgcolor="white",
        node_size=2, node_color="#9aa0a6",
        edge_color="#c0c4c8", edge_linewidth=0.6,
        figsize=(10, 10),
    )

    # Short line from each station to the intersection it snapped to.
    for _, row in chargers.iterrows():
        node = G.nodes[row["node"]]
        ax.plot([row["longitude"], node["x"]], [row["latitude"], node["y"]],
                color="#1a73e8", linewidth=0.5, alpha=0.6, zorder=3)

    ax.scatter(chargers["longitude"], chargers["latitude"], s=14,
               color="#1a73e8", edgecolor="white", linewidth=0.4,
               zorder=4, label=f"DC fast chargers ({len(chargers)})")

    ax.set_title(title, fontsize=13)
    ax.legend(loc="lower left", frameon=True)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="massachusetts",
                        help="Geofabrik US state name (massachusetts, rhode-island) or a city in CITIES (boston)")
    parser.add_argument("--states", nargs="+", default=["MA"],
                        help="State codes for chargers, e.g. MA RI")
    parser.add_argument("--roads", choices=["major", "all"], default="major",
                        help="major = highways and main roads, all = every drivable street")
    args = parser.parse_args()

    road_types = ALL_ROADS if args.roads == "all" else MAJOR_ROADS
    G = load_street_graph(args.region, road_types)
    chargers = load_chargers(args.states)
    if args.region in CITIES:
        west, south, east, north = CITIES[args.region][1]
        chargers = chargers[chargers["longitude"].between(west, east)
                            & chargers["latitude"].between(south, north)]
    chargers = snap_chargers(G, chargers)

    # Count each two-way road once, not once per direction.
    total_miles = sum(d["miles"] for _, _, d in ox.convert.to_undirected(G).edges(data=True))
    print(f"Street graph: {len(G.nodes):,} intersections, {len(G.edges):,} road segments, "
          f"{total_miles:,.0f} miles of road")
    print(f"Chargers on the map: {len(chargers)}")

    FIGURE_DIR.mkdir(exist_ok=True)
    out_path = FIGURE_DIR / f"network_{args.region}_{args.roads}.png"
    region_name = args.region.replace("-", " ").title()
    if args.region in CITIES:
        region_name += " area"
    road_label = "every street" if args.roads == "all" else "major roads"
    plot_network(G, chargers, f"{region_name} {road_label} and DC fast chargers", out_path)
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
