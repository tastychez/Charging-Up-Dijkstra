r"""Compare A* + Haversine and A* + Manhattan with EV battery limits.

From the repository root, in Windows PowerShell:
    .\.venv\Scripts\python.exe -m AStar.main --start "Dallas, TX" --goal "Boston, MA" --full-range 250 --starting-range 100

Offline learning example:
    .\.venv\Scripts\python.exe -m AStar.main --demo
"""

import argparse
import csv
import hashlib
import json
import re
import statistics
import sys
import urllib.error
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

# Also permit: python AStar/main.py from the repository root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astar import astar
from heuristics import prepare_heuristic, validate_coordinates
from AStar.battery_routes import battery_legs, build_charging_graph, demo_data, validate_ranges
from AStar.data import load_road_miles


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def compare_searches(graph, coordinates, source, target, methods, trials):
    """Separate heuristic preparation from repeated, interleaved search timing."""
    prepared, preparation_ms = {}, {}
    for method in methods:
        begin = perf_counter()
        prepared[method] = prepare_heuristic(graph, coordinates, target, method)
        preparation_ms[method] = (perf_counter() - begin) * 1000
        astar(graph, source, target, prepared[method])  # Untimed warm-up.
    samples = {method: [] for method in methods}
    for trial in range(trials):
        order = methods if trial % 2 == 0 else methods[::-1]
        for method in order:
            begin = perf_counter()
            astar(graph, source, target, prepared[method])
            samples[method].append((perf_counter() - begin) * 1000)
    runs = {}
    for method in methods:
        stats = {}
        answer = astar(graph, source, target, prepared[method], stats)
        median = statistics.median(samples[method])
        quartiles = statistics.quantiles(samples[method], n=4, method="inclusive") if trials > 1 else [median] * 3
        runs[method] = dict(answer=answer, stats=stats, heuristic=prepared[method],
                            preparation_ms=preparation_ms[method], median_ms=median,
                            q1_ms=quartiles[0], q3_ms=quartiles[2])
    return runs


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    starts = parser.add_mutually_exclusive_group()
    starts.add_argument("--start", help="listed station/city name; default Dallas, TX")
    starts.add_argument("--start-coords", nargs=2, type=float, metavar=("LAT", "LON"))
    goals = parser.add_mutually_exclusive_group()
    goals.add_argument("--goal", help="listed station/city name; default Boston, MA")
    goals.add_argument("--goal-coords", nargs=2, type=float, metavar=("LAT", "LON"))
    parser.add_argument("--full-range", "--range", dest="full_range", type=float,
                        help="miles after a full recharge; default 250, or 15 in --demo")
    parser.add_argument("--starting-range", type=float,
                        help="miles left at departure; default full range, or 5 in --demo")
    parser.add_argument("--heuristic", choices=("haversine", "manhattan", "both"), default="both")
    parser.add_argument("--trials", type=int, default=101, help="timed trials per heuristic (default 101)")
    parser.add_argument("--demo", action="store_true", help="small illustrative example, no downloads")
    parser.add_argument("--offline", action="store_true", help="require an existing road-distance cache")
    parser.add_argument("--list-stations", action="store_true", help="print endpoint names and exit")
    parser.add_argument("--no-plot", action="store_true", help="omit the static comparison plot")
    parser.add_argument("--animate", action="store_true", help="also save interactive animation.html (open it in a browser)")
    parser.add_argument("--basemap", action="store_true", help="download/cache OSM background tiles")
    parser.add_argument("--road-shapes", action="store_true", help="download/cache actual road geometry for chosen legs")
    parser.add_argument("--output", type=Path, help="output folder; default AStar/results/<trip settings>")
    args = parser.parse_args(argv)
    if args.trials < 1:
        parser.error("--trials must be at least 1.")
    if args.demo and (args.basemap or args.road_shapes):
        parser.error("The demo has illustrative roads; omit --basemap and --road-shapes.")
    if args.offline and (args.basemap or args.road_shapes):
        parser.error("Offline runs use plain graph plots; omit --basemap and --road-shapes.")
    return parser, args


def main(argv=None):
    parser, args = parse_args(argv)
    if args.demo:
        coordinates, road_miles, chargers, default_start, default_goal = demo_data()
        if args.start_coords or args.goal_coords:
            parser.error("Custom coordinates need real road data; omit --demo.")
    else:
        from Dijkstra.stations import END, START, STATIONS
        coordinates = dict(STATIONS)
        chargers = set(STATIONS) - {START, END}
        default_start, default_goal = END, START  # Texas -> Boston; either direction is supported.
    if args.list_stations:
        print("\n".join(coordinates))
        return 0
    source, target = args.start or default_start, args.goal or default_goal
    if args.start_coords:
        source = "Custom start"
        coordinates[source] = tuple(args.start_coords)
    if args.goal_coords:
        target = "Custom destination"
        coordinates[target] = tuple(args.goal_coords)
    full_range = args.full_range if args.full_range is not None else (15 if args.demo else 250)
    starting_range = args.starting_range if args.starting_range is not None else (min(5, full_range) if args.demo else full_range)
    try:
        validate_ranges(starting_range, full_range)
        for point in coordinates.values():
            validate_coordinates(*point)
        if source not in coordinates or target not in coordinates:
            raise ValueError("Unknown start/destination name. Use --list-stations or --start-coords/--goal-coords.")
        if not args.demo:
            road_miles = load_road_miles(coordinates, args.offline)
        begin = perf_counter()
        graph = build_charging_graph(road_miles, source, target, full_range, starting_range, chargers)
        graph_ms = (perf_counter() - begin) * 1000
        methods = ["haversine", "manhattan"] if args.heuristic == "both" else [args.heuristic]
        runs = compare_searches(graph, coordinates, source, target, methods, args.trials)
    except (ValueError, OSError, urllib.error.URLError) as error:
        parser.error(str(error))

    slug = lambda name: re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    coord_key = hashlib.sha256(json.dumps(coordinates, sort_keys=True).encode()).hexdigest()[:8]
    folder = args.output or ROOT / "AStar" / "results" / (
        f"{slug(source)}_to_{slug(target)}_start{starting_range:g}_full{full_range:g}_{coord_key}")
    folder.mkdir(parents=True, exist_ok=True)
    print(f"\n{source} -> {target}")
    print(f"Starting range: {starting_range:g} mi | Full-charge range: {full_range:g} mi")
    print(f"Charging graph: {len(graph)} vertices, {sum(map(len, graph.values()))} directed edges")
    print(f"Graph construction: {graph_ms:.4f} ms (excluded from search timing)")
    if args.demo:
        print("DEMO: illustrative distances, not measured road routes.")
    else:
        print("DATA: selected corridor sites; rounded mileage along OSRM's fastest routes.")

    comparisons, h_rows, summaries = [], [], {}
    for method, run in runs.items():
        prepared = run["heuristic"]
        answer = run["answer"]
        path, miles = answer if answer is not None else (None, None)
        legs = battery_legs(path, graph, starting_range, full_range) if path is not None else []
        remaining = legs[-1].range_on_arrival if legs else (starting_range if path is not None else None)
        row = dict(heuristic=method, vertices=len(graph), edges=sum(map(len, graph.values())),
                   full_range=full_range, starting_range=starting_range,
                   total_miles=miles, charging_stops=max(0, len(path) - 2) if path else None,
                   arrival_range=remaining, expanded=run["stats"]["expanded"],
                   edge_checks=run["stats"]["edge_checks"], scale=prepared.scale,
                   raw_inconsistent_edges=prepared.raw_inconsistent_edges,
                   preparation_ms=run["preparation_ms"], median_search_ms=run["median_ms"],
                   q1_search_ms=run["q1_ms"], q3_search_ms=run["q3_ms"], trials=args.trials)
        comparisons.append(row)
        summaries[method] = dict(**row, path=path, legs=[asdict(leg) for leg in legs],
                                  expanded_order=run["stats"]["expanded_order"])
        h_rows.extend(dict(heuristic=method, node=node, raw_h=prepared.raw_values[node],
                           scale=prepared.scale, used_h=prepared.values[node]) for node in graph)
        print(f"\nA* + {method}: scale {prepared.scale:.6f}; {prepared.raw_inconsistent_edges} raw inconsistent edges")
        print(f"  Expanded: {run['stats']['expanded']} | Edge checks: {run['stats']['edge_checks']}")
        print(f"  Heuristic preparation: {run['preparation_ms']:.4f} ms")
        print(f"  Median search: {run['median_ms']:.4f} ms over {args.trials} trials")
        if path is None:
            print("  No feasible route for these battery limits and available stations.")
        else:
            print("  Route: " + " -> ".join(path))
            print(f"  Total: {miles:g} mi | Charging stops: {max(0, len(path)-2)} | Arrival range: {remaining:g} mi")
            for leg in legs:
                refill = f"; recharge to {leg.range_after_stop:g}" if leg.recharged else ""
                print(f"    {leg.source} -> {leg.target}: {leg.miles:g} mi; range {leg.range_before:g} -> {leg.range_on_arrival:g}{refill}")
            write_csv(folder / f"battery_{method}.csv", [asdict(leg) for leg in legs])
    write_csv(folder / "comparison.csv", comparisons)
    write_csv(folder / "heuristics.csv", h_rows)
    shared = dict(source=source, target=target, full_range=full_range, starting_range=starting_range,
                  coordinates={node: coordinates[node] for node in graph}, graph=graph)
    (folder / "graph.json").write_text(json.dumps(shared, indent=2), encoding="utf-8")
    summary = dict(**{key: value for key, value in shared.items() if key != "graph"},
                   dataset="illustrative demo" if args.demo else "shared Boston-Dallas corridor / OSRM rounded miles",
                   graph_preparation_ms=graph_ms, methods=summaries)
    (folder / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if not args.no_plot:
        from AStar.visualize import plot_comparison
        plot_comparison(graph, coordinates, source, target, runs, starting_range, full_range,
                        folder / "comparison.png", basemap=args.basemap, road_shapes=args.road_shapes,
                        demo=args.demo)
    if args.animate:
        from AStar.animation import write_animation
        write_animation(graph, coordinates, source, target, runs, starting_range, full_range,
                        folder / "animation.html", basemap=args.basemap,
                        road_shapes=args.road_shapes, demo=args.demo)
        print(f"\nOpen this animation in your browser: {folder / 'animation.html'}")
    print(f"\nResults saved to: {folder}")
    return 0 if any(run["answer"] is not None for run in runs.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
