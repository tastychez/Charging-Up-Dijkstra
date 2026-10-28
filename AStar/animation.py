"""Export a self-contained, interactive A* search and EV-drive animation.

Search focus is distinct from car motion. The fixed charging graph is revealed
as A* expands nodes; the car moves only after predecessor backtracking finishes.
During car playback, the local reachable map uses arrival range, then full range
after a selected recharge. Rendering and trace collection are never benchmarked.
"""

import base64
import io
import json
from dataclasses import asdict
from pathlib import Path

from astar import astar
from AStar.battery_routes import battery_legs
from AStar.visualize import mercator


def make_story(graph, source, target, run, starting_range, full_range, labels=None):
    """Record the real A* trace, backtrack, then replay the chosen driving legs."""
    trace = []
    labels = labels or {}
    name = lambda node: labels.get(node,str(node))
    answer = astar(graph, source, target, run["heuristic"], trace=trace, trace_compact=len(graph)>200)
    if answer != run["answer"]:
        raise ValueError("The recorded search differs from the benchmarked search.")
    frames = [dict(phase="start", current=source, budget=starting_range,
                   title="Start and destination", message="The car is at the start. Choose a heuristic and step through the trip."),
              dict(phase="build", current=source, budget=starting_range,
                   title="Build the starting reachable map",
                   message="Only complete driving legs that fit the starting range are connected to the start.")]
    for index, step in enumerate(trace):
        node = step["current"]
        budget = starting_range if node == source else (0 if node == target else full_range)
        frames.append(dict(phase="search", trace_index=index, current=node, budget=budget,
                           title=f"A* search: inspect {name(node)}",
                           message="Destination popped: its shortest distance is now known." if step["is_goal"] else
                           "Reveal this candidate stop's feasible driving legs and update cheaper routes. The car has not moved."))
    if answer is None:
        frames.append(dict(phase="failed", current=source, budget=starting_range,
                           title="No battery-feasible route",
                           message="The frontier is empty. These sites and range limits cannot connect the start to the destination."))
        return dict(trace=trace, frames=frames, path=None, legs=[])

    path, total_miles = answer
    previous = trace[-1]["previous"]
    reverse_path = [target]
    frames.append(dict(phase="backtrack", current=target, reverse_path=list(reverse_path),
                       title="Backtrack from the destination",
                       message="Follow the saved predecessor links to recover the route before driving."))
    while reverse_path[-1] != source:
        child = reverse_path[-1]
        parent = previous[child]
        reverse_path.append(parent)
        frames.append(dict(phase="backtrack", current=parent, reverse_path=list(reverse_path),
                           title=f"Backtrack: {name(child)} to {name(parent)}",
                           message=f"The predecessor of {name(child)} is {name(parent)}. This reads the answer backward; the car is still at the start."))

    legs = battery_legs(path, graph, starting_range, full_range)
    frames.append(dict(phase="drive", kind="departure", current=source, car_node=source,
                       budget=starting_range, remaining=starting_range, driven=0,
                       title="Drive the selected route", message="Planning is finished. Now the car follows the recovered route."))
    driven = 0.0
    for index, leg in enumerate(legs):
        for progress in (0.25, 0.5, 0.75):
            frames.append(dict(phase="drive", kind="motion", current=leg.source,
                               car_leg=index, progress=progress, remaining=leg.range_before-leg.miles*progress,
                               driven=driven+leg.miles*progress,
                               title=f"Driving: {name(leg.source)} to {name(leg.target)}",
                               message="Range decreases along this driving leg. Passing a charger does not force a stop."))
        driven += leg.miles
        frames.append(dict(phase="drive", kind="arrival", current=leg.target, car_node=leg.target,
                           budget=leg.range_on_arrival, remaining=leg.range_on_arrival, driven=driven,
                           title=f"Arrive at {name(leg.target)}",
                           message="The reachable map now uses the range actually left on arrival. A refill has not happened yet."))
        if leg.recharged:
            frames.append(dict(phase="drive", kind="charge", current=leg.target, car_node=leg.target,
                               budget=full_range, remaining=full_range, driven=driven,
                               title=f"Recharge at {name(leg.target)}",
                               message="Refill to full range. The local reachable map grows; the planned route continues from here."))
    remaining = legs[-1].range_on_arrival if legs else starting_range
    frames.append(dict(phase="complete", current=target, car_node=target,
                       budget=remaining, remaining=remaining, driven=total_miles,
                       title="Destination reached",
                       message=f"Trip complete: {total_miles:g} driving miles. The remaining range is {remaining:g} miles."))
    return dict(trace=trace, frames=frames, path=path, legs=[asdict(leg) for leg in legs])


def write_animation(graph, coordinates, source, target, runs, starting_range,
                    full_range, output, basemap=False, road_shapes=False, demo=False,
                    labels=None, route_shapes=None, background_roads=None, dataset_label=None):
    """Create one HTML file containing both heuristics, controls, data, and map."""
    width, height, margin = 1000, 600, 42
    raw_points = {node: mercator(*coordinates[node]) for node in graph}
    xs, ys = zip(*raw_points.values())
    span_x, span_y = max(max(xs)-min(xs), 1000), max(max(ys)-min(ys), 1000)
    left, bottom = min(xs)-span_x*0.06, min(ys)-span_y*0.09
    right, top = max(xs)+span_x*0.06, max(ys)+span_y*0.09
    scale = min((width-2*margin)/(right-left), (height-2*margin)/(top-bottom))
    x_offset = (width-(right-left)*scale)/2
    y_offset = (height-(top-bottom)*scale)/2

    def project(point):
        return [round(x_offset+(point[0]-left)*scale, 3), round(y_offset+(top-point[1])*scale, 3)]

    payload = dict(source=source, target=target, starting_range=starting_range, full_range=full_range,
                   points={node: project(point) for node, point in raw_points.items()},
                   graph=graph, methods={}, background=None, shapes=[],
                   demo=demo, road_shapes=road_shapes, width=width, height=height,
                   labels=labels or {}, dataset_label=dataset_label,
                   local_road_shapes=route_shapes is not None,
                   edge_count=sum(map(len,graph.values())), background_paths="")
    if background_roads:
        paths=[]
        for line in background_roads:
            points=[project(mercator(*point)) for point in line]
            if points:
                paths.append("M"+" L".join(f"{x},{y}" for x,y in points))
        payload["background_paths"]=" ".join(paths)
    if basemap or (road_shapes and route_shapes is None):
        from Dijkstra.realmap import basemap as get_basemap, road_shape
    if basemap:
        latitudes, longitudes = zip(*(coordinates[node] for node in graph))
        image, extent = get_basemap(min(latitudes)-1.1, min(longitudes)-1.1,
                                   max(latitudes)+1.1, max(longitudes)+1.1, zoom=6)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        origin = project((extent[0], extent[3]))
        payload["background"] = dict(url="data:image/png;base64,"+base64.b64encode(buffer.getvalue()).decode(),
                                     x=origin[0], y=origin[1], width=(extent[1]-extent[0])*scale,
                                     height=(extent[3]-extent[2])*scale)
    shapes = {}
    for method, run in runs.items():
        story = make_story(graph, source, target, run, starting_range, full_range, labels)
        payload["methods"][method] = dict(**story, total_miles=None if run["answer"] is None else run["answer"][1],
                                         scale=run["heuristic"].scale, h=run["heuristic"].values,
                                         raw_h=run["heuristic"].raw_values, median_ms=run["median_ms"],
                                         expanded=run["stats"]["expanded"], preparation_ms=run["preparation_ms"])
        if road_shapes and story["path"]:
            for first, second in zip(story["path"], story["path"][1:]):
                if (first, second) not in shapes:
                    line = route_shapes[first,second] if route_shapes is not None else road_shape(coordinates[first], coordinates[second])
                    shapes[first, second] = [project(mercator(*point)) for point in line]
    payload["shapes"] = [dict(source=first, target=second, points=points)
                         for (first, second), points in shapes.items()]
    # Prevent a station name containing HTML from closing the embedded data tag.
    encoded = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    template = Path(__file__).with_name("animation_template.html").read_text(encoding="utf-8")
    Path(output).write_text(template.replace("__ANIMATION_DATA__", encoded), encoding="utf-8")
    return payload
