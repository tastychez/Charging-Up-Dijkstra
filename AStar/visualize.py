"""Make poster-ready route and runtime comparisons, outside search timing."""

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from math import log, pi, radians, tan


def mercator(lat, lon):
    """Map coordinates without loading the teammate's network/API helpers."""
    radius_meters = 6378137
    return radius_meters * radians(lon), radius_meters * log(tan(pi / 4 + radians(lat) / 2))


def plot_comparison(graph, coordinates, source, target, runs, starting_range,
                    full_range, output, basemap=False, road_shapes=False, demo=False):
    if basemap or road_shapes:
        from Dijkstra.realmap import basemap as get_basemap, road_shape

    colors = {"haversine": "#1469b8", "manhattan": "#d7761d"}
    methods = list(runs)
    figure = plt.figure(figsize=(15, 9.5), facecolor="white")
    grid = figure.add_gridspec(2, len(methods), height_ratios=[3.4, 1.1],
                              left=0.06, right=0.97, bottom=0.12, top=0.86,
                              hspace=0.28, wspace=0.2)
    points = {node: mercator(*coordinates[node]) for node in graph}
    latitudes = [coordinates[node][0] for node in graph]
    longitudes = [coordinates[node][1] for node in graph]
    padding = 0.04 if demo else 1.1
    south, north = min(latitudes) - padding, max(latitudes) + padding
    west, east = min(longitudes) - padding, max(longitudes) + padding
    west = max(-179.9, west)
    east = min(179.9, east)
    south, north = max(-80, south), min(80, north)
    bottom_left, top_right = mercator(south, west), mercator(north, east)
    background = None
    if basemap:
        background = get_basemap(south, west, north, east, zoom=6)

    shapes = {}
    if road_shapes:
        for run in runs.values():
            if run["answer"] is not None:
                path = run["answer"][0]
                for first, second in zip(path, path[1:]):
                    if (first, second) not in shapes:
                        shapes[first, second] = [mercator(*point) for point in road_shape(coordinates[first], coordinates[second])]

    for column, method in enumerate(methods):
        run = runs[method]
        color = colors[method]
        axis = figure.add_subplot(grid[0, column])
        if background is not None:
            axis.imshow(background[0], extent=background[1], alpha=0.55, zorder=0)
        seen = set()
        for first, neighbors in graph.items():
            for second in neighbors:
                pair = frozenset((first, second))
                if pair not in seen:
                    seen.add(pair)
                    axis.plot([points[first][0], points[second][0]],
                              [points[first][1], points[second][1]],
                              color="#8d99a5", alpha=0.22, linewidth=0.6, zorder=1)
        expanded = set(run["stats"]["expanded_order"])
        for node, (x, y) in points.items():
            axis.scatter(x, y, s=22, color=color if node in expanded else "#c4cbd2",
                         edgecolors="white", linewidths=0.4, zorder=3)
        answer = run["answer"]
        if answer is not None:
            path, miles = answer
            for first, second in zip(path, path[1:]):
                line = shapes.get((first, second), [points[first], points[second]])
                axis.plot([point[0] for point in line], [point[1] for point in line],
                          color=color, linewidth=2.5, linestyle="-" if road_shapes else "--", zorder=4)
            for index, node in enumerate(path[1:-1], start=1):
                x, y = points[node]
                axis.scatter(x, y, s=50, color=color, edgecolors="white", zorder=5)
                axis.annotate(str(index), (x, y), xytext=(4, -13), textcoords="offset points",
                              fontsize=8, bbox=dict(facecolor="white", alpha=0.85, edgecolor="none", pad=0.6), zorder=7)
            subtitle = f"{miles:g} miles | {max(0, len(path)-2)} charging stops"
        else:
            subtitle = "No feasible route at these battery limits"
        for node, label, marker, endpoint_color in [
            (source, "Start", "o", "#20864d"), (target, "Goal", "*", "#b52d35")]:
            x, y = points[node]
            axis.scatter(x, y, s=90, marker=marker, color=endpoint_color, edgecolors="white", zorder=8)
            axis.annotate(label, (x, y), xytext=(6, 8), textcoords="offset points", fontsize=9,
                          bbox=dict(facecolor="white", alpha=0.85, edgecolor="none", pad=1), zorder=9)
        axis.set_title(f"A* + {method.capitalize()}\n{subtitle}\n"
                       f"Scale {run['heuristic'].scale:.3f}; {run['stats']['expanded']} valid pops", fontsize=10)
        axis.set_xlim(bottom_left[0], top_right[0])
        axis.set_ylim(bottom_left[1], top_right[1])
        axis.set_aspect("equal")
        axis.set_xticks([])
        axis.set_yticks([])
        for spine in axis.spines.values():
            spine.set_edgecolor("#cdd3da")

    if len(methods) == 2:
        count_axis = figure.add_subplot(grid[1, 0])
        time_axis = figure.add_subplot(grid[1, 1])
    else:
        lower = grid[1, 0].subgridspec(1, 2, wspace=0.45)
        count_axis = figure.add_subplot(lower[0, 0])
        time_axis = figure.add_subplot(lower[0, 1])
    labels = [method.capitalize() for method in methods]
    bar_colors = [colors[method] for method in methods]
    counts = [runs[method]["stats"]["expanded"] for method in methods]
    count_axis.barh(labels, counts, color=bar_colors, height=0.5)
    count_axis.set_xlim(0, max(counts, default=1) * 1.2 + 1)
    count_axis.set_xlabel("Valid heap pops, including the destination", fontsize=9)
    count_axis.set_title("Search work", fontsize=10)
    for row, value in enumerate(counts):
        count_axis.text(value + 0.3, row, str(value), va="center", fontsize=9)
    times = [runs[method]["median_ms"] for method in methods]
    errors = [[runs[method]["median_ms"] - runs[method]["q1_ms"] for method in methods],
              [runs[method]["q3_ms"] - runs[method]["median_ms"] for method in methods]]
    time_axis.barh(labels, times, xerr=errors, capsize=4, color=bar_colors, height=0.5)
    time_axis.set_xlim(left=0)
    time_axis.set_xlabel("Median search time (ms); bars show the interquartile range", fontsize=9)
    time_axis.set_title("Prepared-heuristic A* search only", fontsize=10)
    for axis in (count_axis, time_axis):
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="x", alpha=0.15)
        axis.set_axisbelow(True)
    figure.suptitle(f"{source} to {target}\n"
                   f"Starting range {starting_range:g} miles | Full-charge range {full_range:g} miles | "
                   f"{len(graph)} sites, {sum(map(len, graph.values()))} directed legs", fontsize=14, y=0.97)
    legend = [Line2D([0], [0], color="#8d99a5", linewidth=1, label="Feasible connections (directions stored in graph)"),
              Line2D([0], [0], marker="o", color="none", markerfacecolor="#20864d", label="Start"),
              Line2D([0], [0], marker="*", color="none", markerfacecolor="#b52d35", label="Destination")]
    figure.legend(handles=legend, loc="upper center", bbox_to_anchor=(0.5, 0.905), ncol=3, frameon=False, fontsize=9)
    description = "Illustrative road distances." if demo else "Distances: OSRM fastest-route mileage, rounded to whole miles; selected corridor sites."
    route_note = "Colored routes follow OSRM road geometry." if road_shapes else "Dashed route connectors show chosen stop pairs, not road geometry."
    map_note = " Map: OpenStreetMap contributors." if basemap else ""
    figure.text(0.5, 0.025, description + map_note + "\n" + route_note +
                " Gray connectors show battery feasibility. Charging time is excluded.", ha="center", fontsize=8, color="#4a5662")
    figure.savefig(output, dpi=180, facecolor="white")
    plt.close(figure)
