r"""Our A* on the teammate's full OSM/AFDC dataset, with no library routing calls.

Run from the repo root:
    .\.venv\Scripts\python.exe -m AStar.full_map --start "Dallas, TX" --goal "Boston, MA" --starting-range 100 --full-range 250 --animate --output AStar/results/full_trip

The first run may download the region's raw roads and chargers. All mapped
charger vertices are included. Starting/full range are literal usable miles;
there is no implicit 80% multiplier or 10,000-mile penalty for charging stops.
"""

import argparse
from dataclasses import asdict
import gzip
import json
from pathlib import Path
import re
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from AStar.battery_routes import battery_legs, validate_ranges
from AStar.full_data import background_roads, load_full_trip, road_route_shapes
from AStar.main import compare_searches, write_csv
from heuristics import validate_coordinates


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    starts = parser.add_mutually_exclusive_group()
    starts.add_argument("--start")
    starts.add_argument("--start-coords", nargs=2, type=float, metavar=("LAT", "LON"))
    goals = parser.add_mutually_exclusive_group()
    goals.add_argument("--goal")
    goals.add_argument("--goal-coords", nargs=2, type=float, metavar=("LAT", "LON"))
    parser.add_argument("--region", default="dallas-boston", help="region supported by your teammate's data.py")
    parser.add_argument("--roads", choices=("highways", "major", "route", "all"), default="route")
    parser.add_argument("--full-range", type=float, default=250, help="usable miles after a full recharge")
    parser.add_argument("--starting-range", type=float, help="usable miles left now; default full range")
    parser.add_argument("--network", default="all", help="all networks by default; use Tesla for Superchargers only")
    parser.add_argument("--heuristic", choices=("haversine", "manhattan", "both"), default="both")
    parser.add_argument("--trials", type=int, default=11, help="search timings per heuristic, excluding preparation")
    parser.add_argument("--animate", action="store_true", help="write a self-contained animation.html")
    parser.add_argument("--no-plot", action="store_true", help="omit comparison.png")
    parser.add_argument("--offline", action="store_true", help="require cached street/charger/geocode inputs")
    parser.add_argument("--max-endpoint-snap", type=float, default=2.0, help="maximum endpoint access gap, in miles")
    parser.add_argument("--output", type=Path, default=Path("AStar/results/full_trip"))
    args = parser.parse_args(argv)
    args.starting_range = args.full_range if args.starting_range is None else args.starting_range
    if args.trials < 1:
        parser.error("--trials must be at least 1.")
    if not 0 <= args.max_endpoint_snap < float("inf"):
        parser.error("--max-endpoint-snap must be finite and nonnegative.")
    try:
        validate_ranges(args.starting_range, args.full_range)
        for point in (args.start_coords, args.goal_coords):
            if point is not None:
                validate_coordinates(*point)
    except ValueError as error:
        parser.error(str(error))
    return parser, args


def main(argv=None):
    parser, args = parse_args(argv)
    defaults = {"massachusetts":("Pittsfield, MA", "Provincetown, MA"),
                "boston":("Boston, MA", "Cambridge, MA")}
    default_start, default_goal = defaults.get(args.region,("Dallas, TX", "Boston, MA"))
    start = args.start or ("Custom start" if args.start_coords else default_start)
    goal = args.goal or ("Custom destination" if args.goal_coords else default_goal)
    print(f"\n{start} -> {goal}; region {args.region}; networks {args.network}", flush=True)
    print("Loading the full dataset and preparing road mileage with our own heap search.", flush=True)
    begin = perf_counter()
    try:
        trip = load_full_trip(args.region, args.roads, start, goal, args.starting_range,
                             args.full_range, args.start_coords, args.goal_coords,
                             args.network, args.offline, args.max_endpoint_snap)
    except (ValueError, KeyError, OSError) as error:
        parser.error(re.sub(r"(api_key=)[^&\s]+", r"\1[redacted]", str(error)))
    preparation_ms = (perf_counter()-begin)*1000
    graph, coordinates = trip.graph, trip.coordinates
    edge_count = sum(map(len, graph.values()))
    print(f"Trip graph: {len(graph):,} vertices including endpoints, {edge_count:,} directed legs", flush=True)
    print(f"Starting range {args.starting_range:g} mi; full-charge range {args.full_range:g} mi", flush=True)
    print("Objective: minimum total miles; full refills at selected intermediate chargers.", flush=True)
    print("Preparing both heuristics and timing our A* searches...", flush=True)
    methods = ["haversine", "manhattan"] if args.heuristic == "both" else [args.heuristic]
    runs = compare_searches(graph, coordinates, "START", "END", methods, args.trials)
    args.output.mkdir(parents=True, exist_ok=True)
    comparisons, heuristic_rows, summaries = [], [], {}
    for method, run in runs.items():
        answer, prepared = run["answer"], run["heuristic"]
        path, miles = answer if answer is not None else (None, None)
        legs = battery_legs(path, graph, args.starting_range, args.full_range) if path else []
        arrival = legs[-1].range_on_arrival if legs else None
        row = dict(heuristic=method, vertices=len(graph), directed_edges=edge_count,
                   total_miles=miles, charging_stops=max(0,len(path)-2) if path else None,
                   arrival_range=arrival, expanded=run["stats"]["expanded"],
                   edge_checks=run["stats"]["edge_checks"], scale=prepared.scale,
                   raw_inconsistent_edges=prepared.raw_inconsistent_edges,
                   preparation_ms=run["preparation_ms"], median_search_ms=run["median_ms"],
                   q1_search_ms=run["q1_ms"], q3_search_ms=run["q3_ms"], trials=args.trials)
        comparisons.append(row)
        readable_legs = [dict(asdict(leg), source_name=trip.labels[leg.source],
                              target_name=trip.labels[leg.target]) for leg in legs]
        summaries[method] = dict(**row, path=path, path_names=[trip.labels[n] for n in path] if path else None,
                                  legs=readable_legs, expanded_order=run["stats"]["expanded_order"])
        heuristic_rows.extend(dict(heuristic=method, node=node, name=trip.labels[node],
                                   raw_h=prepared.raw_values[node], used_h=prepared.values[node],
                                   scale=prepared.scale) for node in graph)
        print(f"\nA* + {method}: scale {prepared.scale:.6f}; expanded {row['expanded']:,}; "
              f"median search {run['median_ms']:.4f} ms", flush=True)
        if path is None:
            print("  No route fits these ranges and the loaded roads/chargers.")
        else:
            print(f"  {miles:,.2f} miles; {row['charging_stops']} charging stops; {arrival:.2f} miles left")
            for leg in legs:
                suffix = f"; recharge to {leg.range_after_stop:g}" if leg.recharged else ""
                print(f"    {trip.labels[leg.source]} -> {trip.labels[leg.target]}: {leg.miles:.2f} mi; "
                      f"range {leg.range_before:.2f} -> {leg.range_on_arrival:.2f}{suffix}")
        write_csv(args.output/f"battery_{method}.csv", readable_legs)
    write_csv(args.output/"comparison.csv", comparisons)
    write_csv(args.output/"heuristics.csv", heuristic_rows)
    shared = dict(source="START", target="END", starting_range=args.starting_range,
                  full_range=args.full_range, coordinates=coordinates, labels=trip.labels,
                  details=trip.details)
    (args.output/"summary.json").write_text(json.dumps(
        dict(**shared, input_and_graph_preparation_ms=preparation_ms, methods=summaries),indent=2),encoding="utf-8")
    with gzip.open(args.output/"graph.json.gz", "wt", encoding="utf-8") as file:
        json.dump(dict(**shared, graph=graph), file, separators=(",", ":"))
    if args.animate or not args.no_plot:
        shapes = road_route_shapes(trip, runs)
        roads = background_roads(trip.street_graph)
        if not args.no_plot:
            from AStar.full_visualize import plot_full_comparison
            plot_full_comparison(trip, runs, args.starting_range, args.full_range, shapes, roads,
                                 args.output/"comparison.png")
        if args.animate:
            from AStar.animation import write_animation
            description = (f"Full {args.region} road/charger dataset: {trip.details['mapped_station_records']:,} "
                           f"station records represented by {trip.details['charger_vertices']:,} charger intersections. "
                           "Every mapped charger vertex is included. Road distances use our own heap searches. "
                           "Charger/endpoint access links approximate off-network travel with direct distances.")
            write_animation(graph, coordinates, "START", "END", runs, args.starting_range,
                            args.full_range, args.output/"animation.html", road_shapes=True,
                            labels=trip.labels, route_shapes=shapes, background_roads=roads,
                            dataset_label=description)
            print(f"\nOpen the animation: {(args.output/'animation.html').resolve()}")
    print(f"Results saved to: {args.output.resolve()}")
    return 0 if any(run["answer"] is not None for run in runs.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
