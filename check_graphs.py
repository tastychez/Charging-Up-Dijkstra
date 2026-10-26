"""Check that the street graph, charger graph and trip planner are correct.

Every check prints PASS or FAIL. Run this after rebuilding any data.

Usage:
    python check_graphs.py
    python check_graphs.py --region massachusetts
"""

import argparse
import random

import networkx as nx
import numpy as np
import osmnx as ox

import data
import search
from charger_graph import MAX_LEG_MILES, charger_stations, load_charger_graph
from trip import plan_trip

failures = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if not ok:
        failures.append(name)


def straight_line_miles(lat1, lon1, lat2, lon2):
    return ox.distance.great_circle(lat1, lon1, lat2, lon2) / data.METERS_PER_MILE


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="dallas-boston")
    parser.add_argument("--roads", choices=list(data.ROAD_LEVELS), default="route")
    parser.add_argument("--trip", nargs=2, default=None, help="start and end places to test")
    args = parser.parse_args()
    road_types = data.ROAD_LEVELS[args.roads]
    random.seed(0)

    print(f"Street graph ({args.region})")
    G = data.load_street_graph(args.region, road_types)
    D = data.routing_graph(G)
    print(f"      {len(D):,} intersections, {D.number_of_edges():,} road segments")
    check("every intersection can reach every other one", nx.is_strongly_connected(D))
    check("no road loops back to the same intersection", nx.number_of_selfloops(D) == 0)
    miles = np.array([d["miles"] for _, _, d in D.edges(data=True)])
    check("every road segment has a positive length", (miles > 0).all(),
          f"{(miles <= 0).sum()} with length 0")
    check("every intersection has coordinates",
          all("x" in d and "y" in d for _, d in D.nodes(data=True)))
    too_short = 0
    for u, v, d in D.edges(data=True):
        a, b = D.nodes[u], D.nodes[v]
        if d["miles"] < straight_line_miles(a["y"], a["x"], b["y"], b["x"]) * 0.999 - 0.01:
            too_short += 1
    check("no road segment is shorter than the straight line between its ends", too_short == 0,
          f"{too_short} too short")

    print("\nChargers")
    stations = charger_stations(G, args.region)
    all_chargers = data.load_chargers(data.region_states(args.region))
    check("every charger location is an intersection in the street graph",
          stations["node"].isin(D.nodes).all())
    check("every kept charger is within 2 miles of the road network",
          (stations["snap_miles"] <= 2).all(),
          f"{stations['stations'].sum():,} of {len(all_chargers):,} chargers kept at "
          f"{len(stations):,} intersections, median {stations['snap_miles'].median():.2f} mi away")

    print("\nCharger graph")
    C = load_charger_graph(args.region, MAX_LEG_MILES, road_types)
    print(f"      {C.number_of_nodes():,} charger locations, {C.number_of_edges():,} legs")
    legs = list(C.edges(data=True))
    check("no leg is longer than the longest range we test",
          all(d["miles"] <= MAX_LEG_MILES + 1e-6 for _, _, d in legs))
    check("every leg includes the detour into and out of both chargers",
          all(abs(d["miles"] - (C.nodes[u]["snap_miles"] + d["road_miles"] + C.nodes[v]["snap_miles"])) < 1e-3
              for u, v, d in legs))
    sample = random.sample(legs, min(100, len(legs)))
    worst = max(abs(nx.dijkstra_path_length(D, u, v, weight="miles") - d["road_miles"])
                for u, v, d in sample)
    check("leg distances match NetworkX's Dijkstra on 100 random legs", worst < 1e-3,
          f"worst difference {worst:.6f} mi")
    shortcut = sum(1 for u, v, d in sample
                   if d["road_miles"] < straight_line_miles(C.nodes[u]["lat"], C.nodes[u]["lon"],
                                                            C.nodes[v]["lat"], C.nodes[v]["lon"]) - 4.01)
    check("no leg is shorter than the straight line between its chargers", shortcut == 0)

    print("\nTrip")
    start, end = args.trip or (("Dallas, TX", "Boston, MA") if args.region == "dallas-boston"
                               else ("Pittsfield, MA", "Provincetown, MA"))
    for range_miles in (150, 250, 300):
        trip = plan_trip(start, end, range_miles, args.region, road_types)
        usable = trip["usable_miles"]
        route = trip["route"]
        check(f"{range_miles} mi range: every leg fits on one charge",
              all(leg["miles"] <= usable + 1e-6 for leg in trip["legs"]),
              f"{len(trip['stops']) - 2} stops, {trip['total_miles']:,.1f} mi, longest leg "
              f"{max(leg['miles'] for leg in trip['legs']):.1f} of {usable:.0f}")
        check(f"{range_miles} mi range: route follows real roads from start to end",
              route[0] == trip["start"]["node"] and route[-1] == trip["end"]["node"]
              and all(D.has_edge(u, v) for u, v in zip(route, route[1:])))
        road_total = sum(D[u][v]["miles"] for u, v in zip(route, route[1:]))
        detours = trip["start"]["snap_miles"] + trip["end"]["snap_miles"] + \
            2 * sum(C.nodes[n]["snap_miles"] for n in trip["stops"][1:-1])
        check(f"{range_miles} mi range: total miles = roads driven + detours",
              abs(road_total + detours - trip["total_miles"]) < 1e-2)
        T = trip["trip_graph"]
        for weight in ("cost", "miles"):
            length = lambda path: sum(T[a][b][weight] for a, b in zip(path, path[1:]))
            expected = length(nx.dijkstra_path(T, "START", "END", weight=weight))
            ours = {name: length(search.ALGORITHMS[name](T, "START", "END", weight))
                    for name in ("dijkstra", "astar")}
            check(f"{range_miles} mi range: our Dijkstra and A* match NetworkX on {weight}",
                  all(abs(v - expected) < 1e-6 for v in ours.values()))

    print(f"\n{'All checks passed' if not failures else f'{len(failures)} checks failed'}")


if __name__ == "__main__":
    main()
