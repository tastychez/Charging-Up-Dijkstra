"""Compare Dijkstra (h=0), A* Haversine, and A* scaled Manhattan in one engine.

Put this file in AStar/ beside benchmark_networkx.py, then run from the repo root:
    python -X utf8 -m AStar.benchmark_same_scope

All three call the unchanged root astar.astar with identical bookkeeping.
Dijkstra here means that shared search with every estimate set to zero. It is
not a timing of the separate Dijkstra/dijkstra.py implementation.

Uses the existing saved-graph loader from benchmark_networkx.py. Folder paths
and exported result ZIPs are supported. Existing trip results are read only.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial
import gc
from hashlib import sha256
import json
from pathlib import Path
import statistics
from time import perf_counter_ns

from AStar import benchmark_networkx as saved
from astar import astar

TRIALS = 11
METHODS = ("dijkstra", "haversine", "manhattan")
LABELS = {"dijkstra": "Dijkstra (h=0)", "haversine": "A* Haversine",
          "manhattan": "A* Scaled Manhattan"}
SCOPE_NOTE = ("Controlled heuristic comparison in the same handwritten astar.astar engine. "
              "Dijkstra uses h=0 and shares all A* bookkeeping, including equal-mileage "
              "fewer-legs tie-breaking. This does not benchmark Dijkstra/dijkstra.py.")


@dataclass
class Case:
    method: str
    values: dict
    search: object


def cases_for(dataset):
    """Change only the estimate dictionary; use the same callback and engine."""
    values = {"dijkstra": dict.fromkeys(dataset.graph, 0.0), **dataset.estimates}
    source, target = dataset.summary["source"], dataset.summary["target"]
    return [Case(method, values[method], partial(
        astar, dataset.graph, source, target,
        heuristic=values[method].__getitem__, stats=None, trace=None)) for method in METHODS]


def validate_route(dataset, returned):
    """Check full directed, battery-feasible, optimal route outside the timer."""
    saved.require(returned is not None, "The shared search returned no route")
    path, reported_miles = returned
    summary = dataset.summary
    saved.require(path and path[0] == summary["source"] and path[-1] == summary["target"],
                  "Incorrect route endpoints")
    saved.require(len(path) == len(set(path)), "A returned route repeats a node")
    total, remaining = 0.0, summary["starting_range"]
    for index, (node, neighbor) in enumerate(zip(path, path[1:])):
        saved.require(neighbor in dataset.graph.get(node, {}), "Invalid directed edge in route")
        miles = dataset.graph[node][neighbor]
        saved.require(miles <= remaining + saved.MILEAGE_TOLERANCE, "Route exceeds usable range")
        total += miles
        remaining -= miles
        if index < len(path) - 2:
            saved.require(neighbor not in (summary["source"], summary["target"]), "Invalid intermediate stop")
            remaining = summary["full_range"]
    saved.require(saved.same_miles(reported_miles, total), "Returned mileage differs from route mileage")
    for method in saved.METHODS:
        saved.require(saved.same_miles(total, summary["methods"][method]["total_miles"]),
                      "Route does not match saved optimal mileage")
    return dict(path=list(path), total_miles=total, charging_stops=max(0, len(path) - 2),
                arrival_usable_miles=remaining, directed_edges_valid=True, battery_valid=True)


def estimate_digest(values):
    return sha256(json.dumps(values, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def measure(dataset, trials=TRIALS, progress=print):
    cases = cases_for(dataset)
    digests = {case.method: estimate_digest(case.values) for case in cases}
    samples = {case.method: [] for case in cases}
    routes = {case.method: [] for case in cases}
    trials_rows, orders = [], []
    for case in cases:
        validate_route(dataset, case.search())  # Exactly one untimed warm-up.
    for trial in range(trials):
        offset = trial % len(cases)
        order = cases[offset:] + cases[:offset]
        orders.append([case.method for case in order])
        for position, case in enumerate(order, 1):
            began = perf_counter_ns()
            returned = case.search()  # Search and route reconstruction only.
            elapsed_ns = perf_counter_ns() - began
            checked = validate_route(dataset, returned)
            samples[case.method].append(elapsed_ns / 1e6)
            routes[case.method].append(checked)
            trials_rows.append(dict(trip=dataset.spec.title, method=LABELS[case.method], trial=trial + 1,
                                    execution_position=position, elapsed_ns=elapsed_ns,
                                    search_ms=elapsed_ns / 1e6, total_miles=checked["total_miles"],
                                    charging_stops=checked["charging_stops"]))
            del returned
        if trial in (0, trials // 2, trials - 1):
            progress(f"  {dataset.spec.title}: trial {trial + 1}/{trials} completed for all three methods.")

    rows, methods = [], {}
    for case in cases:
        # One additional, untimed audit AFTER all timing, to collect search work.
        stats = {}
        audited = validate_route(dataset, case.search(stats=stats))
        last = routes[case.method][-1]
        saved.require(audited["path"] == last["path"], "Tracing/statistics changed the route")
        saved_order = dataset.summary["methods"].get(case.method, {}).get("expanded_order")
        if saved_order is not None:
            saved.require(stats["expanded_order"] == saved_order, "Saved expansion order changed")
        saved.require(estimate_digest(case.values) == digests[case.method], "Heuristic values changed")
        quartiles = statistics.quantiles(samples[case.method], n=4, method="inclusive")
        row = dict(trip=dataset.spec.title, method=LABELS[case.method],
                   implementation="Shared handwritten astar.astar", vertices=len(dataset.graph),
                   directed_edges=dataset.spec.edges, starting_range=dataset.summary["starting_range"],
                   full_range=dataset.summary["full_range"], trials=trials,
                   median_search_ms=statistics.median(samples[case.method]),
                   q1_search_ms=quartiles[0], q3_search_ms=quartiles[2],
                   expanded=stats["expanded"], edge_checks=stats["edge_checks"],
                   total_miles=last["total_miles"], charging_stops=last["charging_stops"],
                   same_engine=True, stats_during_timing=False, trace_during_timing=False)
        rows.append(row)
        methods[case.method] = dict(**row, samples_ms=samples[case.method],
                                    heuristic_values_sha256=digests[case.method],
                                    heuristic_scale=0.0 if case.method == "dijkstra" else
                                        dataset.summary["methods"][case.method]["scale"],
                                    route=last, untimed_statistics=stats,
                                    validated_timed_routes=len(routes[case.method]),
                                    all_timed_paths_equal=all(route["path"] == last["path"] for route in routes[case.method]))
    return rows, methods, trials_rows, orders


def protected_sources():
    paths = {"shared_search_engine": saved.ROOT / "astar.py", "heuristics": saved.ROOT / "heuristics.py",
             "saved_dataset_loader": Path(saved.__file__), "this_benchmark": Path(__file__)}
    return {name: dict(path=str(path.resolve()), sha256=sha256(path.read_bytes()).hexdigest())
            for name, path in paths.items()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    results = Path(__file__).resolve().parent / "results"
    parser.add_argument("--dallas", type=Path, default=results / saved.SPECS[0].folder)
    parser.add_argument("--buffalo", type=Path, default=results / saved.SPECS[1].folder)
    parser.add_argument("--output", type=Path, default=results / "same_scope_benchmark_windows")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    for path in (args.dallas, args.buffalo):
        saved.require(not path.is_dir() or path.resolve() != output, "Use a separate benchmark output folder")
    protected = protected_sources()
    report = dict(created_utc=datetime.now(timezone.utc).isoformat(), environment=saved.machine_info(),
                  scope_note=SCOPE_NOTE, source_code=protected,
                  protocol=dict(engine="The same root astar.astar function for all three methods",
                                dijkstra_mode="All precomputed h values are zero; f=g",
                                timed_trials_per_configuration=TRIALS, untimed_warmups_per_configuration=1,
                                statistics_audits_after_timing_per_configuration=1,
                                timed="Search and route reconstruction", handwritten_kwargs=dict(stats=None, trace=None),
                                execution_order="Rotate the three methods each trial; never run concurrently",
                                excluded=["loading", "graph validation", "heuristic preparation and validation",
                                          "route validation", "statistics collection", "tracing", "printing", "export"],
                                tie_breaking="Fewer driving legs when mileage is exactly equal",
                                maximum_usable_range=200, starting_usable_range=200,
                                objective="minimum total driving miles"),
                  trips=[], results=[], raw_trials=[])
    print(SCOPE_NOTE, flush=True)
    for spec, path in zip(saved.SPECS, (args.dallas, args.buffalo)):
        print(f"Loading and checking {spec.title}: {path}", flush=True)
        dataset = saved.load_dataset(path, spec)
        print(f"  All three methods share {len(dataset.graph):,} vertices and {spec.edges:,} directed edges.", flush=True)
        rows, methods, raw, order = measure(dataset)
        report["trips"].append(dict(trip=spec.title, vertices=len(dataset.graph), directed_edges=spec.edges,
                                    provenance=dataset.provenance, methods=methods, execution_orders=order))
        report["results"].extend(rows)
        report["raw_trials"].extend(raw)
        del dataset
        gc.collect()
    saved.require(len(report["results"]) == 6 and len(report["raw_trials"]) == 66, "Incomplete benchmark")
    saved.require(protected_sources() == protected, "A source file changed during benchmarking")
    for trip in report["trips"]:
        provenance = trip["provenance"]
        with saved.SavedInput(provenance["input"]) as source:
            for name, key in (("summary.json", "summary_sha256"), ("graph.json.gz", "graph_gzip_sha256"),
                              ("heuristics.csv", "heuristics_csv_sha256")):
                saved.require(source.digest(name) == provenance[key], "A saved dataset changed")
    report["validation"] = dict(all_66_timed_routes_checked=True, all_6_warmups_checked=True,
                                six_statistics_audits_outside_timing=True, equal_optimal_mileage_verified=True,
                                directed_battery_constraints_verified=True, same_graph_and_same_engine=True,
                                source_and_saved_results_unchanged=True)
    output.mkdir(parents=True, exist_ok=True)
    saved.write_csv(output / "comparison.csv", report["results"])
    saved.write_csv(output / "trials.csv", report["raw_trials"])
    (output / "benchmark.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("\nTrip | Shared-engine method | Median ms | Expanded | Edge checks | Miles | Stops")
    for row in report["results"]:
        print(f"{row['trip']} | {row['method']} | {row['median_search_ms']:.2f} | {row['expanded']:,} | "
              f"{row['edge_checks']:,} | {row['total_miles']:.2f} | {row['charging_stops']}")
    print(f"\nAll checks passed. Saved: {output}")
    return report


if __name__ == "__main__":
    main()
