"""Plan an EV trip by combining the street graph and the charger graph.

1. Look up the start and end places and match each to its nearest intersection.
2. Add START and END to a copy of the charger graph, connected to every charger
   the car can reach on one charge.
3. Find the shortest path from START to END in that graph. The vertices along it
   are the charging stops. Edges are weighted by `cost` (miles plus a large amount
   per leg), so the route with the fewest stops wins, then the shortest one.
4. Turn each leg back into the actual roads with a shortest path on the street graph.

`find_path` is the algorithm used in step 3. It defaults to NetworkX's Dijkstra
until our own Dijkstra and A* are ready. Any function with the same signature as
networkx.dijkstra_path(graph, source, target, weight) can be passed in.

Usage:
    python trip.py "Dallas, TX" "Boston, MA"
    python trip.py "Dallas, TX" "Boston, MA" --range 150
    python trip.py "Pittsfield, MA" "Provincetown, MA" --region massachusetts --range 80
"""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import osmnx as ox
from matplotlib.collections import LineCollection
from scipy.sparse.csgraph import dijkstra

import data
from charger_graph import load_charger_graph, street_matrix

FIGURE_DIR = Path(__file__).parent / "figures"
GEOCODE_CACHE = data.DATA_DIR / "geocode.json"
BUFFER = 0.8  # only plan legs that use at most 80 percent of the car's range
# When choosing a route, every leg also costs this many miles. It is larger than
# any trip, so the route with the fewest charging stops always wins, and among
# routes with that many stops the shortest one wins. Reported miles never include it.
# Dallas to Boston at 250 miles: 9 stops and 1,774.0 miles, instead of 11 stops
# and 1,773.1 miles when only miles count.
STOP_COST_MILES = 10_000


def geocode(place):
    """Return (lat, lon) for a place name, using OpenStreetMap's place search."""
    cache = json.loads(GEOCODE_CACHE.read_text()) if GEOCODE_CACHE.exists() else {}
    if place not in cache:
        cache[place] = list(ox.geocode(place))
        GEOCODE_CACHE.write_text(json.dumps(cache, indent=1))
    return tuple(cache[place])


def _road_path(matrix, nodes, index, a, b, limit):
    """Shortest road path from intersection a to intersection b, as a list of node ids."""
    dist, pred = dijkstra(matrix, directed=True, indices=index[a],
                          return_predecessors=True, limit=limit)
    path, i = [], index[b]
    while i >= 0:
        path.append(nodes[i])
        i = pred[i]
    return path[::-1]


def plan_trip(start, end, range_miles=250, region="dallas-boston",
              road_types=data.ROUTE_ROADS, find_path=nx.dijkstra_path):
    usable = range_miles * BUFFER
    G = data.load_street_graph(region, road_types)
    matrix, nodes, index = street_matrix(G)
    C = load_charger_graph(region, usable, road_types)

    # Match the start and end to the street graph.
    ends = {}
    for label, place in (("START", start), ("END", end)):
        lat, lon = geocode(place)
        node, meters = ox.distance.nearest_nodes(G, X=lon, Y=lat, return_dist=True)
        ends[label] = {"place": place, "lat": lat, "lon": lon, "node": node,
                       "snap_miles": meters / data.METERS_PER_MILE}

    # Road miles from START to every charger, and from every charger to END.
    chargers = list(C.nodes)
    rows = np.array([index[n] for n in chargers])
    from_start = dijkstra(matrix, indices=index[ends["START"]["node"]], limit=usable)
    to_end = dijkstra(matrix.T.tocsr(), indices=index[ends["END"]["node"]], limit=usable)

    T = C.copy()
    for label, info in ends.items():
        T.add_node(label, name=info["place"], lat=info["lat"], lon=info["lon"],
                   snap_miles=info["snap_miles"])
    s_snap, e_snap = ends["START"]["snap_miles"], ends["END"]["snap_miles"]
    for c, r in zip(chargers, rows):
        c_snap = C.nodes[c]["snap_miles"]
        if s_snap + from_start[r] + c_snap <= usable:
            T.add_edge("START", c, miles=s_snap + from_start[r] + c_snap, road_miles=from_start[r])
        if c_snap + to_end[r] + e_snap <= usable:
            T.add_edge(c, "END", miles=c_snap + to_end[r] + e_snap, road_miles=to_end[r])
    direct = from_start[index[ends["END"]["node"]]]
    if s_snap + direct + e_snap <= usable:
        T.add_edge("START", "END", miles=s_snap + direct + e_snap, road_miles=direct)

    for _, _, d in T.edges(data=True):
        d["cost"] = d["miles"] + STOP_COST_MILES
    try:
        stops = find_path(T, "START", "END", weight="cost")
    except nx.NetworkXNoPath:
        raise SystemExit(f"No route: a car with {range_miles} miles of range can't make this trip "
                         f"with legs under {usable:.0f} miles.")

    # Street-level route for every leg.
    street_nodes = {"START": ends["START"]["node"], "END": ends["END"]["node"]}
    legs, route = [], []
    for a, b in zip(stops, stops[1:]):
        path = _road_path(matrix, nodes, index, street_nodes.get(a, a), street_nodes.get(b, b), usable)
        route.extend(path if not route else path[1:])
        legs.append({"from": T.nodes[a]["name"], "to": T.nodes[b]["name"], "miles": T[a][b]["miles"]})

    return {
        "start": ends["START"], "end": ends["END"], "range_miles": range_miles,
        "usable_miles": usable, "stops": stops, "legs": legs, "route": route,
        "total_miles": sum(leg["miles"] for leg in legs), "trip_graph": T, "G": G,
    }


def _edge_line(G, u, v):
    """Coordinates of the shortest road segment from u to v, following its curve."""
    d = min(G[u][v].values(), key=lambda e: e["miles"])
    if "geometry" in d:
        return list(d["geometry"].coords)
    return [(G.nodes[u]["x"], G.nodes[u]["y"]), (G.nodes[v]["x"], G.nodes[v]["y"])]


def _road_type(edge):
    """Road type of an edge, e.g. "motorway". Merged edges can list several types."""
    kind = edge.get("highway", "")
    if isinstance(kind, list):
        kind = kind[0]
    return kind.replace("_link", "")


def plot_trip(trip, out_path):
    G, T = trip["G"], trip["trip_graph"]
    fig, ax = plt.subplots(figsize=(14, 9))

    # Background: highways only, so the map stays readable.
    lines = [_edge_line(G, u, v) for u, v, d in G.edges(data=True)
             if _road_type(d) in ("motorway", "trunk")]
    ax.add_collection(LineCollection(lines, colors="#c9cdd2", linewidths=0.5, zorder=1))

    chargers = [n for n in T if n not in ("START", "END")]
    ax.scatter([T.nodes[n]["lon"] for n in chargers], [T.nodes[n]["lat"] for n in chargers],
               s=3, color="#9cc3f5", zorder=2, label=f"Charger locations ({len(chargers):,})")

    route = trip["route"]
    route_lines = [_edge_line(G, u, v) for u, v in zip(route, route[1:])]
    ax.add_collection(LineCollection(route_lines, colors="#d93025", linewidths=2.2, zorder=3,
                                     label=f"Route ({trip['total_miles']:,.0f} miles)"))

    stops = trip["stops"][1:-1]
    for i, n in enumerate(stops, 1):
        x, y = T.nodes[n]["lon"], T.nodes[n]["lat"]
        ax.scatter(x, y, s=90, color="white", edgecolor="#d93025", linewidth=1.8, zorder=4)
        ax.annotate(str(i), (x, y), ha="center", va="center", fontsize=7, fontweight="bold",
                    color="#d93025", zorder=5)
    for label, color in (("START", "#188038"), ("END", "#202124")):
        info = trip[label.lower()]
        ax.scatter(info["lon"], info["lat"], s=120, marker="*", color=color, zorder=5,
                   label=f"{label.title()}: {info['place']}")

    ax.set_aspect(1 / np.cos(np.radians(np.mean([G.nodes[n]["y"] for n in route]))))
    ax.autoscale()
    ax.set_axis_off()
    ax.set_title(f"{trip['start']['place']} to {trip['end']['place']}, {trip['range_miles']} mile range: "
                 f"{len(stops)} charging stops", fontsize=13)
    ax.legend(loc="lower right", frameon=True, fontsize=9)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("start")
    parser.add_argument("end")
    parser.add_argument("--range", type=int, default=250, help="car range in miles")
    parser.add_argument("--region", default="dallas-boston")
    parser.add_argument("--roads", choices=list(data.ROAD_LEVELS), default="route")
    args = parser.parse_args()

    trip = plan_trip(args.start, args.end, args.range, args.region, data.ROAD_LEVELS[args.roads])
    print(f"{trip['start']['place']} to {trip['end']['place']} with a {args.range} mile range "
          f"(legs up to {trip['usable_miles']:.0f} miles)")
    for i, leg in enumerate(trip["legs"], 1):
        print(f"  Leg {i}: {leg['miles']:6.1f} mi  to {leg['to']}")
    print(f"Total: {trip['total_miles']:,.1f} miles, {len(trip['stops']) - 2} charging stops")

    FIGURE_DIR.mkdir(exist_ok=True)
    slug = lambda s: s.split(",")[0].lower().replace(" ", "-")
    out = FIGURE_DIR / f"trip_{slug(args.start)}_{slug(args.end)}_{args.range}mi.png"
    plot_trip(trip, out)
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
