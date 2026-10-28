"""Benchmark our unchanged A* against unmodified networkx.astar_path.

Run from the repository root with the latest saved trip folders present:
    python -m AStar.benchmark_networkx

--dallas and --buffalo also accept the exported result ZIPs. Only saved graph
weights and saved, checked heuristic values are used. No road routing is rerun.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import gc
import gzip
from hashlib import sha256
import importlib
import io
import json
import math
import os
from pathlib import Path
import platform
import statistics
import sys
from time import get_clock_info, perf_counter_ns
import zipfile

import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from astar import astar as handwritten_astar
from heuristics import haversine_miles, manhattan_miles

TRIALS = 11
WEIGHT = "miles"
MILEAGE_TOLERANCE = 1e-6
CONSISTENCY_TOLERANCE = 1e-8
METHODS = ("haversine", "manhattan")
DISPLAY = {"haversine": "Haversine", "manhattan": "Scaled Manhattan"}
TIE_NOTE = ("Our implementation prefers fewer legs when mileage is exactly equal. "
            "NetworkX may return a different equal-mileage route or stop count; "
            "route identity is not required for correctness.")


@dataclass(frozen=True)
class TripSpec:
    folder: str
    title: str
    vertices: int
    edges: int
    approximate_miles: float
    start_coordinates: tuple | None = None
    goal_coordinates: tuple | None = None


SPECS = (
    TripSpec("full_trip_200_start200_new_data", "Dallas → Boston", 4973, 3260801, 1737.81,
             (32.776272, -96.796856), (42.358834, -71.057830)),
    TripSpec("buffalo_springfield_200_new_data", "Buffalo → Springfield, MO", 2115, 902108, 931.72,
             (42.886416, -78.878149), (37.208173, -93.292271)),
)


@dataclass
class Dataset:
    spec: TripSpec
    summary: dict
    graph: dict
    estimates: dict
    provenance: dict


@dataclass
class Configuration:
    implementation: str
    heuristic: str
    search: object

    @property
    def key(self):
        return f"{self.implementation}/{self.heuristic}"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def same_miles(first, second):
    return math.isclose(first, second, rel_tol=1e-10, abs_tol=MILEAGE_TOLERANCE)


class SavedInput:
    """Read fixed filenames from a results directory or ZIP without extracting it."""
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.archive = None
        self.members = {}

    def __enter__(self):
        if self.path.is_file():
            self.archive = zipfile.ZipFile(self.path)
            for member in self.archive.infolist():
                if member.is_dir():
                    continue
                name = member.filename.replace("\\", "/").rsplit("/", 1)[-1]
                if name in ("summary.json", "graph.json.gz", "heuristics.csv"):
                    require(name not in self.members, f"Ambiguous saved filename: {name}")
                    self.members[name] = member.filename
        else:
            require(self.path.is_dir(), f"Saved results were not found: {self.path}")
        return self

    def __exit__(self, *args):
        if self.archive is not None:
            self.archive.close()

    @contextmanager
    def open(self, name):
        if self.archive is not None:
            require(name in self.members, f"{name} is missing from {self.path.name}")
            with self.archive.open(self.members[name]) as file:
                yield file
        else:
            with (self.path / name).open("rb") as file:
                yield file

    def read(self, name):
        with self.open(name) as file:
            return file.read()

    def digest(self, name):
        digest = sha256()
        with self.open(name) as file:
            while block := file.read(1 << 20):
                digest.update(block)
        return digest.hexdigest()


def load_dataset(path, spec):
    with SavedInput(path) as saved:
        summary_bytes = saved.read("summary.json")
        summary = json.loads(summary_bytes)
        with saved.open("graph.json.gz") as file:
            with gzip.GzipFile(fileobj=file) as compressed:
                document = json.load(compressed)
        graph = document["graph"]
        for key in ("source", "target", "starting_range", "full_range", "coordinates", "labels"):
            require(document[key] == summary[key], f"Graph/summary disagree on {key}")
        require(summary["starting_range"] == summary["full_range"] == 200, "Both ranges must be 200 usable miles.")
        require(len(graph) == len(summary["coordinates"]) == spec.vertices, f"Incorrect graph size for {spec.title}")
        require(set(graph) == set(summary["coordinates"]), "Missing graph coordinates")
        source, target = summary["source"], summary["target"]
        require(source in graph and target in graph and source != target, "Invalid endpoints")
        for node, expected_coordinates in ((source, spec.start_coordinates), (target, spec.goal_coordinates)):
            if expected_coordinates is not None:
                require(all(abs(actual - expected) < 1e-5 for actual, expected in
                            zip(summary["coordinates"][node], expected_coordinates)), "Wrong trip direction or endpoint coordinates")

        heuristic_bytes = saved.read("heuristics.csv")
        estimates = {method: {} for method in METHODS}
        raw_estimates = {method: {} for method in METHODS}
        for row in csv.DictReader(io.StringIO(heuristic_bytes.decode("utf-8-sig"))):
            method, node = row["heuristic"], row["node"]
            require(method in METHODS, f"Unknown saved heuristic: {method}")
            require(node not in estimates[method], f"Duplicate saved estimate: {method} {node}")
            value, raw, scale = map(float, (row["used_h"], row["raw_h"], row["scale"]))
            require(all(math.isfinite(v) and v >= 0 for v in (value, raw, scale)), "Invalid heuristic value")
            require(scale == summary["methods"][method]["scale"], "Saved heuristic scales disagree")
            require(math.isclose(value, raw * scale, rel_tol=1e-12, abs_tol=1e-8), "Incorrect scaled estimate")
            estimates[method][node], raw_estimates[method][node] = value, raw
        for method in METHODS:
            require(set(estimates[method]) == set(graph), f"Incomplete {method} estimates")
            require(estimates[method][target] == 0, "The destination estimate must be zero")
            expected = summary["methods"][method]
            require(expected["vertices"] == spec.vertices and expected["directed_edges"] == spec.edges, "Incorrect saved graph counts")
            require(abs(expected["total_miles"] - spec.approximate_miles) <= 0.02, "Unexpected saved trip mileage")
            formula = haversine_miles if method == "haversine" else manhattan_miles
            for node, raw in raw_estimates[method].items():
                calculated = formula(*summary["coordinates"][node], *summary["coordinates"][target])
                require(math.isclose(raw, calculated, rel_tol=1e-12, abs_tol=1e-8), "Saved geographic estimate does not match coordinates")

        edge_count = 0
        for node, neighbors in graph.items():
            for neighbor, miles in neighbors.items():
                require(neighbor in graph, "An edge has an unknown destination")
                require(isinstance(miles, (int, float)) and math.isfinite(miles) and 0 <= miles <= 200, "Invalid or over-range edge")
                require(neighbor != source, "The saved graph has an incoming edge to START")
                for method in METHODS:
                    require(estimates[method][node] <= miles + estimates[method][neighbor] + CONSISTENCY_TOLERANCE,
                            f"The saved {method} heuristic is inconsistent")
                edge_count += 1
        require(not graph[target], "The saved destination should have no outgoing edges")
        require(edge_count == spec.edges, f"Incorrect directed edge count for {spec.title}")
        provenance = {
            "input": str(saved.path),
            "summary_sha256": sha256(summary_bytes).hexdigest(),
            "graph_gzip_sha256": saved.digest("graph.json.gz"),
            "heuristics_csv_sha256": sha256(heuristic_bytes).hexdigest(),
            "heuristic_scales": {m: summary["methods"][m]["scale"] for m in METHODS},
            "all_edges_range_checked": True,
            "both_saved_heuristics_checked_on_every_edge": True,
            "saved_values_reused_without_rescaling": True,
        }
    return Dataset(spec, summary, graph, estimates, provenance)


def networkx_graph(graph):
    converted = nx.DiGraph()
    converted.add_nodes_from(graph)
    converted.add_weighted_edges_from(
        ((node, neighbor, miles) for node, row in graph.items() for neighbor, miles in row.items()),
        weight=WEIGHT,
    )
    require(converted.is_directed() and not converted.is_multigraph(), "Expected a NetworkX DiGraph")
    require(set(converted) == set(graph), "Conversion changed the vertex set")
    require(converted.number_of_edges() == sum(map(len, graph.values())), "Conversion changed the edge count")
    for node, row in graph.items():
        require(set(converted[node]) == set(row), "Conversion changed a directed adjacency")
        for neighbor, miles in row.items():
            require(converted[node][neighbor][WEIGHT] == miles, "Conversion changed an edge's mileage")
    return converted


def configuration_pair(dataset, converted, method):
    source, target = dataset.summary["source"], dataset.summary["target"]
    values = dataset.estimates[method]
    # Both callbacks close over the very same saved estimate dictionary.
    def our_estimate(node):
        return values[node]

    def published_estimate(node, destination):
        return values[node]

    def run_ours():
        return handwritten_astar(dataset.graph, source, target, heuristic=our_estimate, stats=None, trace=None)

    def run_networkx():
        return nx.astar_path(converted, source, target, heuristic=published_estimate, weight=WEIGHT, backend="networkx")

    return (Configuration("handwritten", method, run_ours), Configuration("networkx", method, run_networkx))


def configurations(dataset, converted):
    return [config for method in METHODS for config in configuration_pair(dataset, converted, method)]


def validate_route(dataset, configuration, returned):
    """Always called outside the search timer, including NetworkX mileage sums."""
    require(returned is not None, f"{configuration.key} returned no route")
    if configuration.implementation == "handwritten":
        path, reported_miles = returned
    else:
        path, reported_miles = returned, None
    source, target = dataset.summary["source"], dataset.summary["target"]
    require(path and path[0] == source and path[-1] == target, "Incorrect route endpoints")
    require(len(path) == len(set(path)), "The route repeats a node")
    remaining = dataset.summary["starting_range"]
    total, max_leg, min_arrival = 0.0, 0.0, remaining
    for index, (node, neighbor) in enumerate(zip(path, path[1:])):
        require(node in dataset.graph and neighbor in dataset.graph[node], "The route uses an invalid directed edge")
        miles = dataset.graph[node][neighbor]
        require(miles <= remaining + MILEAGE_TOLERANCE, "The route exceeds its battery budget")
        total += miles
        remaining -= miles
        max_leg, min_arrival = max(max_leg, miles), min(min_arrival, remaining)
        if index < len(path) - 2:
            require(neighbor not in (source, target), "An intermediate stop is an endpoint")
            remaining = dataset.summary["full_range"]
    if reported_miles is not None:
        require(same_miles(reported_miles, total), "Our returned mileage differs from its route")
    expected = dataset.summary["methods"][configuration.heuristic]["total_miles"]
    require(same_miles(total, expected), f"{configuration.key} does not match the saved optimal mileage")
    return dict(path=list(path), total_miles=total, charging_stops=max(0, len(path) - 2),
                maximum_leg_miles=max_leg, minimum_usable_arrival_miles=min_arrival,
                arrival_usable_miles=remaining, directed_edges_valid=True, battery_valid=True)


def measure(dataset, configs, trials=TRIALS, progress=print):
    samples = {config.key: [] for config in configs}
    validated = {config.key: [] for config in configs}
    raw_trials, orders = [], []
    for config in configs:
        validate_route(dataset, config, config.search())  # One untimed warm-up.
    for trial in range(trials):
        offset = trial % len(configs)
        order = configs[offset:] + configs[:offset]
        orders.append([config.key for config in order])
        for position, config in enumerate(order, 1):
            begin = perf_counter_ns()
            returned = config.search()  # Search AND route reconstruction only.
            elapsed_ns = perf_counter_ns() - begin
            # Everything below is deliberately outside the timer.
            checked = validate_route(dataset, config, returned)
            elapsed_ms = elapsed_ns / 1_000_000
            samples[config.key].append(elapsed_ms)
            validated[config.key].append(checked)
            raw_trials.append(dict(trip=dataset.spec.title, implementation=config.implementation,
                                   heuristic=config.heuristic, trial=trial + 1, execution_position=position,
                                   elapsed_ns=elapsed_ns, search_ms=elapsed_ms,
                                   total_miles=checked["total_miles"], charging_stops=checked["charging_stops"]))
        if trial in (0, trials // 2, trials - 1):
            progress(f"  {dataset.spec.title}: completed timed trial {trial + 1}/{trials} for all four configurations.")
    rows, methods = [], {}
    for config in configs:
        values, checks = samples[config.key], validated[config.key]
        quartiles = statistics.quantiles(values, n=4, method="inclusive")
        checked = checks[-1]
        row = dict(trip=dataset.spec.title, implementation=config.implementation,
                   heuristic=config.heuristic, vertices=len(dataset.graph), directed_edges=dataset.spec.edges,
                   starting_range=dataset.summary["starting_range"], full_range=dataset.summary["full_range"],
                   trials=trials, median_search_ms=statistics.median(values),
                   q1_search_ms=quartiles[0], q3_search_ms=quartiles[2],
                   total_miles=checked["total_miles"], charging_stops=checked["charging_stops"],
                   same_mileage_verified=True)
        rows.append(row)
        methods[config.key] = dict(**row, samples_ms=values, route=checked,
                                   validated_timed_routes=len(checks), untimed_warmups=1,
                                   routes_stable_across_trials=all(c["path"] == checked["path"] for c in checks))
    for method in METHODS:
        our = methods[f"handwritten/{method}"]
        published = methods[f"networkx/{method}"]
        require(same_miles(our["total_miles"], published["total_miles"]), "The implementations disagree on mileage")
        for row in rows:
            if row["heuristic"] == method:
                row["same_path_between_implementations"] = our["route"]["path"] == published["route"]["path"]
        our["same_path_as_other_implementation"] = published["same_path_as_other_implementation"] = our["route"]["path"] == published["route"]["path"]
    return rows, methods, raw_trials, orders


def code_hashes():
    published_module = importlib.import_module("networkx.algorithms.shortest_paths.astar")
    files = {"handwritten_astar": ROOT / "astar.py", "heuristics": ROOT / "heuristics.py",
             "published_networkx_astar": Path(published_module.__file__)}
    return {key: dict(path=str(path), sha256=sha256(path.read_bytes()).hexdigest()) for key, path in files.items()}


def machine_info():
    cpu = platform.processor()
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        cpu = next((line.split(":", 1)[1].strip() for line in cpuinfo.read_text().splitlines()
                    if line.startswith("model name")), cpu)
    clock = get_clock_info("perf_counter")
    return dict(platform=platform.platform(), system=platform.system(), cpu=cpu,
                python=sys.version, python_executable=sys.executable, networkx=nx.__version__,
                logical_cpus=os.cpu_count(), gc_enabled=gc.isenabled(),
                clock=dict(name="perf_counter_ns", monotonic=clock.monotonic, resolution_seconds=clock.resolution))


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def plot_results(report, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    colors = {"handwritten": "#1769B5", "networkx": "#259C91"}
    maximum = max(row["q3_search_ms"] for row in report["results"])
    with plt.rc_context({"font.family": "DejaVu Sans", "text.color": "#182C40"}):
        figure, axes = plt.subplots(1, 2, figsize=(16, 9), sharex=True)
        figure.subplots_adjust(left=.14, right=.97, bottom=.24, top=.75, wspace=.48)
        for axis, trip in zip(axes, report["trips"]):
            for offset, implementation in [(-.17, "handwritten"), (.17, "networkx")]:
                rows = [trip["methods"][f"{implementation}/{method}"] for method in METHODS]
                times = [r["median_search_ms"] for r in rows]
                positions = [i + offset for i in range(2)]
                error = [[r["median_search_ms"] - r["q1_search_ms"] for r in rows],
                         [r["q3_search_ms"] - r["median_search_ms"] for r in rows]]
                axis.barh(positions, times, height=.29, color=colors[implementation],
                          xerr=error, capsize=4, error_kw={"elinewidth": 1, "ecolor": "#42566B"})
                for y, value, row in zip(positions, times, rows):
                    axis.text(row["q3_search_ms"] + maximum * .025, y, f"{value:,.2f}",
                              va="center", fontsize=13)
            axis.set_yticks([0, 1], ["Haversine", "Scaled\nManhattan"], fontsize=14)
            axis.invert_yaxis()
            axis.set_xlim(0, maximum * 1.31)
            axis.set_xlabel("Median complete search time (ms)", fontsize=12, labelpad=12)
            axis.set_title(f"{trip['trip']}\n{trip['vertices']:,} vertices · {trip['directed_edges']:,} directed edges",
                           fontsize=16, weight="bold", pad=20)
            axis.spines[["top", "right", "left"]].set_visible(False)
            axis.tick_params(axis="y", length=0)
            axis.tick_params(axis="x", labelsize=11)
            axis.grid(axis="x", color="#E1E6EB", linewidth=.7)
            axis.set_axisbelow(True)
        figure.suptitle("Handwritten A* versus NetworkX A*", fontsize=25, weight="bold", y=.94)
        figure.text(.5, .865, "Same saved graphs and heuristic values · 11 timed trials after one warm-up",
                    ha="center", fontsize=15, color="#42566B")
        figure.legend(handles=[Patch(color=colors[k], label=label) for k, label in
                               [("handwritten", "Our handwritten A*"), ("networkx", "NetworkX astar_path")]],
                      loc="center", bbox_to_anchor=(.5, .145), ncol=2, frameon=False, fontsize=15)
        environment = report["environment"]
        figure.text(.5, .075, f"Measured on {environment['system']} · Python {platform.python_version()} · "
                    f"NetworkX {environment['networkx']} · 200-mile starting and maximum usable range",
                    ha="center", fontsize=11, color="#42566B")
        figure.text(.5, .035, "Error bars: interquartile range. Loading, conversion, heuristic checks, statistics and export excluded.",
                    ha="center", fontsize=10, color="#697887")
        buffer = io.BytesIO()
        figure.savefig(buffer, format="png", dpi=300, facecolor="white")
        output.write_bytes(buffer.getvalue())
        plt.close(figure)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    results = Path(__file__).resolve().parent / "results"
    parser.add_argument("--dallas", type=Path, default=results / SPECS[0].folder)
    parser.add_argument("--buffalo", type=Path, default=results / SPECS[1].folder)
    parser.add_argument("--output", type=Path, default=results / "astar_networkx_benchmark")
    parser.add_argument("--no-plot", action="store_true")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    for saved_path in (args.dallas, args.buffalo):
        require(not saved_path.is_dir() or output != saved_path.resolve(),
                "Use a separate benchmark output folder to preserve the saved trip measurements.")
    protected = code_hashes()
    report = dict(created_utc=datetime.now(timezone.utc).isoformat(), environment=machine_info(),
                  source_code=protected,
                  protocol=dict(timed_trials_per_configuration=TRIALS, untimed_warmups_per_configuration=1,
                                configurations=8, expected_timed_searches=88, weight_attribute=WEIGHT,
                                networkx_backend="networkx", same_session=True,
                                timed="Complete search and route reconstruction",
                                excluded=["loading", "graph conversion", "heuristic preparation and validation",
                                          "statistics collection", "tracing", "animation", "printing", "export",
                                          "NetworkX route mileage calculation"],
                                handwritten_kwargs=dict(stats=None, trace=None),
                                execution_order="Rotate the four configurations by one position each trial",
                                mileage_absolute_tolerance=MILEAGE_TOLERANCE,
                                heuristic_consistency_tolerance=CONSISTENCY_TOLERANCE),
                  tie_breaking_note=TIE_NOTE, trips=[], results=[], raw_trials=[])
    for spec, path in zip(SPECS, (args.dallas, args.buffalo)):
        print(f"Loading and validating {spec.title}: {path}", flush=True)
        dataset = load_dataset(path, spec)
        print(f"Converting and checking every directed edge: {spec.vertices:,} vertices, {spec.edges:,} edges.", flush=True)
        converted = networkx_graph(dataset.graph)
        rows, methods, trials, order = measure(dataset, configurations(dataset, converted))
        report["trips"].append(dict(trip=spec.title, vertices=spec.vertices, directed_edges=spec.edges,
                                    source=dataset.summary["source"], target=dataset.summary["target"],
                                    starting_range=200, maximum_usable_range=200, objective="minimum total driving miles",
                                    provenance=dataset.provenance, methods=methods, execution_orders=order))
        report["results"].extend(rows)
        report["raw_trials"].extend(trials)
        del dataset, converted
        gc.collect()
    require(len(report["results"]) == 8 and len(report["raw_trials"]) == 88, "Incomplete benchmark")
    require(code_hashes() == protected, "An algorithm source file changed during benchmarking")
    for trip in report["trips"]:
        provenance = trip["provenance"]
        with SavedInput(provenance["input"]) as saved:
            for filename, key in (("summary.json", "summary_sha256"),
                                  ("graph.json.gz", "graph_gzip_sha256"),
                                  ("heuristics.csv", "heuristics_csv_sha256")):
                require(saved.digest(filename) == provenance[key], "A saved dataset changed during benchmarking")
    report["validation"] = dict(all_88_timed_routes_checked=True, all_8_warmup_routes_checked=True,
                                equal_optimal_mileage_verified=True, directed_battery_constraints_verified=True,
                                networkx_algorithm_source_unchanged=True, handwritten_algorithm_source_unchanged=True,
                                saved_datasets_and_benchmark_measurements_unchanged=True)
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "comparison.csv", report["results"])
    write_csv(output / "trials.csv", report["raw_trials"])
    (output / "benchmark.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if not args.no_plot:
        plot_results(report, output / "astar_networkx_comparison.png")
    print("\nTrip | Heuristic | Handwritten median ms | NetworkX median ms | Miles | Stops (ours / NetworkX)")
    for trip in report["trips"]:
        for method in METHODS:
            our, published = (trip["methods"][f"{implementation}/{method}"] for implementation in ("handwritten", "networkx"))
            print(f"{trip['trip']} | {DISPLAY[method]} | {our['median_search_ms']:.2f} | "
                  f"{published['median_search_ms']:.2f} | {our['total_miles']:.2f} | "
                  f"{our['charging_stops']} / {published['charging_stops']}")
    print(f"\nAll checks passed. Saved: {output}")
    return report


if __name__ == "__main__":
    main()
