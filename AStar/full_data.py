"""Adapt the teammate's full road/charger inputs to our battery-feasible graph.

Only data loading, graph containers, and spatial matching come from libraries.
All road routing uses our RoadNetwork heap search; the stop search uses astar.py.
All mapped charger intersections are kept. No station-count cap or corridor
shortlist is applied. As in charger_graph.py, shared intersections are merged
and the nearest station represents them, with the source-record count retained.
When supplied, the region's chargers_...pkl provides its exact station rows;
its precomputed edges are not used by our searches.
"""

from dataclasses import dataclass
import gzip
import hashlib
import json
from math import isfinite
from pathlib import Path
import pickle
from time import perf_counter

from AStar.battery_routes import validate_ranges
from AStar.road_search import RoadNetwork
from heuristics import validate_coordinates


@dataclass
class FullTrip:
    graph: dict
    coordinates: dict
    labels: dict
    locations: dict
    street_graph: object
    roads: RoadNetwork
    details: dict


def charger_records(street_graph, stations, shared_data, network="all", mapped_input=False):
    """Use the same snapping, two-mile cutoff, and grouping as the new dataset."""
    def record_count(frame):
        return int(frame["stations"].sum()) if mapped_input else len(frame)

    if mapped_input and any(not isfinite(float(value)) or float(value) < 1
                            or float(value) != int(value) for value in stations["stations"]):
        raise ValueError("The saved charger table contains invalid station counts.")
    original = record_count(stations)
    if network != "all":
        stations = stations[stations["ev_network"].fillna("").str.casefold() == network.casefold()]
    selected = record_count(stations)
    if selected:
        if mapped_input:
            mapped = stations.copy()
            missing = set(mapped["node"]) - set(street_graph.nodes)
            if missing:
                raise ValueError("The saved charger table does not match the street file. "
                                 "Copy both corrected .pkl files for this region into data/.")
            if any(not isfinite(float(value)) or not 0 <= float(value) <= 2.0
                   for value in mapped["snap_miles"]):
                raise ValueError("The saved charger table contains invalid access distances.")
        else:
            mapped = shared_data.snap_chargers(street_graph, stations)
    else:
        mapped = stations.copy()
    kept = record_count(mapped)
    records = {}
    if kept:
        counts = (mapped.groupby("node")["stations"].sum() if mapped_input
                  else mapped.groupby("node").size())
        mapped = mapped.sort_values("snap_miles").drop_duplicates("node")
        for row in mapped.itertuples():
            key = f"charger:{row.node}"
            city, state = str(row.city), str(row.state)
            name = str(row.station_name)
            records[key] = dict(road_node=row.node, lat=float(row.latitude), lon=float(row.longitude),
                                snap_miles=float(row.snap_miles), name=name,
                                label=f"{city}, {state} · {name}", stations=int(counts[row.node]),
                                network=str(row.ev_network))
    return records, dict(downloaded_station_records=None if mapped_input else original,
                         selected_station_records=selected,
                         mapped_station_records=kept, charger_vertices=len(records),
                         omitted_outside_snap_cutoff=None if mapped_input else selected-kept,
                         network=network)


def saved_station_table(path):
    """Read the supplied station rows, without using its library-computed edges."""
    with Path(path).open("rb") as file:
        saved = pickle.load(file)
    if not isinstance(saved, dict) or "stations" not in saved:
        raise ValueError("The saved charger file must contain a stations table.")
    stations = saved["stations"]
    required = {"node", "latitude", "longitude", "snap_miles", "station_name",
                "city", "state", "ev_network", "stations"}
    if not hasattr(stations, "columns") or not required <= set(stations.columns):
        raise ValueError("The saved charger file has an unsupported stations table.")
    if stations["node"].duplicated().any():
        raise ValueError("The saved charger table must have one row per road intersection.")
    # The supplied `edges` are intentionally not returned. Charger-to-charger
    # road distances are still prepared by our own RoadNetwork heap searches.
    return stations


def charger_connections(roads, records, full_range, cache_dir, progress=print):
    """Prepare all battery-feasible charger legs with our own bounded searches."""
    signature = hashlib.sha256(json.dumps(
        [(key, str(row["road_node"]), row["snap_miles"], row["lat"], row["lon"])
         for key, row in records.items()], separators=(",", ":")).encode()).hexdigest()
    metadata = dict(schema=1, algorithm="own_heap_search", road_signature=roads.signature,
                    station_signature=signature, full_range=float(full_range))
    key = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()[:20]
    path = Path(cache_dir) / f"charger_legs_{key}.json.gz"
    if path.exists():
        with gzip.open(path, "rt", encoding="utf-8") as file:
            saved = json.load(file)
        if saved.get("metadata") == metadata:
            progress(f"Using our cached road legs: {path.name}")
            return saved["graph"], True
    graph = {key: {} for key in records}
    at_road = {roads.index[row["road_node"]]: key for key, row in records.items()}
    targets = set(at_road)
    last_update = perf_counter()
    progress(f"Preparing real road legs for all {len(records):,} mapped charger locations (own heap search)...")
    for number, (source, row) in enumerate(records.items(), 1):
        origin = roads.index[row["road_node"]]
        distances = roads.reachable(origin, full_range-row["snap_miles"], targets=targets)
        for target_road, road_miles in distances.items():
            target = at_road[target_road]
            if target == source:
                continue
            miles = row["snap_miles"] + road_miles + records[target]["snap_miles"]
            if miles <= full_range:
                graph[source][target] = miles
        if perf_counter()-last_update >= 2 or number == len(records):
            progress(f"  Prepared {number:,}/{len(records):,} charger locations")
            last_update = perf_counter()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+".part")
    with gzip.open(temporary, "wt", encoding="utf-8") as file:
        json.dump(dict(metadata=metadata, graph=graph), file, separators=(",", ":"))
    temporary.replace(path)
    return graph, False


def endpoint_info(place, coordinates, street_graph, shared_data, max_snap=2.0):
    """Resolve a place once; coordinates bypass geocoding entirely."""
    import osmnx as ox
    if coordinates is None:
        cache_path = shared_data.DATA_DIR / "geocode.json"
        cached = json.loads(cache_path.read_text()) if cache_path.exists() else {}
        if place not in cached:
            cached[place] = list(ox.geocode(place))
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(cached, indent=2), encoding="utf-8")
        coordinates = cached[place]
    lat, lon = map(float, coordinates)
    validate_coordinates(lat, lon)
    node, meters = ox.distance.nearest_nodes(street_graph, X=lon, Y=lat, return_dist=True)
    snap = float(meters) / shared_data.METERS_PER_MILE
    if snap > max_snap:
        raise ValueError(f"{place} is {snap:.2f} miles from the loaded road network; "
                         "choose a covered location/region or explicitly raise --max-endpoint-snap.")
    return dict(road_node=node, lat=lat, lon=lon, snap_miles=snap, name=place, label=place)


def assemble_trip(roads, records, connections, start, goal, starting_range, full_range):
    """Add endpoints. First legs use current range; charger departures use full range."""
    validate_ranges(starting_range, full_range)
    graph = {key: dict(connections[key]) for key in records}
    graph["START"], graph["END"] = {}, {}
    start_row, goal_row = roads.index[start["road_node"]], roads.index[goal["road_node"]]
    targets = {roads.index[row["road_node"]] for row in records.values()}
    from_start = roads.reachable(start_row, starting_range-start["snap_miles"],
                                 targets=targets | {goal_row})
    to_goal = roads.reachable(goal_row, full_range-goal["snap_miles"], targets=targets, reverse=True)
    for key, row in records.items():
        road_row = roads.index[row["road_node"]]
        outward = from_start.get(road_row)
        if outward is not None:
            miles = start["snap_miles"]+outward+row["snap_miles"]
            if miles <= starting_range:
                graph["START"][key] = miles
        inward = to_goal.get(road_row)
        if inward is not None:
            miles = row["snap_miles"]+inward+goal["snap_miles"]
            if miles <= full_range:
                graph[key]["END"] = miles
    # Being at the same geographic endpoint is a zero-mile trip, even when it
    # is not exactly on an included road intersection.
    same = (start["lat"], start["lon"]) == (goal["lat"], goal["lon"])
    direct = from_start.get(goal_row)
    if same:
        graph["START"]["END"] = 0.0
    elif direct is not None:
        miles = start["snap_miles"]+direct+goal["snap_miles"]
        if miles <= starting_range:
            graph["START"]["END"] = miles
    return graph


def load_full_trip(region, road_level, start_place, goal_place, starting_range, full_range,
                   start_coordinates=None, goal_coordinates=None, network="all", offline=False,
                   max_endpoint_snap=2.0):
    """Read the teammate's raw datasets, not his library-based trip planner."""
    import data as shared_data
    validate_ranges(starting_range, full_range)
    if not all(hasattr(shared_data,name) for name in ("ROAD_LEVELS","region_states","load_street_graph","load_chargers")):
        raise ValueError("The root data.py is still the older version. Merge the latest origin/main before running AStar.full_map.")
    road_types = shared_data.ROAD_LEVELS[road_level]
    states = shared_data.region_states(region)
    street_path = shared_data.DATA_DIR / f"streets_{region}_{len(road_types)}types.pkl"
    station_path = shared_data.DATA_DIR / f"chargers_{region}_{len(road_types)}types.pkl"
    if offline:
        required = [street_path]
        if not station_path.exists():
            required.append(shared_data.DATA_DIR / f"chargers_{'_'.join(states)}.csv")
        missing = [path.name for path in required if not path.exists()]
        if missing:
            raise ValueError("Missing local input files: "+", ".join(missing)+
                             ". Run online once, or copy the matching data/ files from your teammate.")
        if start_coordinates is None or goal_coordinates is None:
            geocodes = shared_data.DATA_DIR / "geocode.json"
            known = json.loads(geocodes.read_text()) if geocodes.exists() else {}
            if (start_coordinates is None and start_place not in known) or (goal_coordinates is None and goal_place not in known):
                raise ValueError("Offline endpoint names need cached geocodes; use --start-coords/--goal-coords.")
    graph = shared_data.load_street_graph(region, road_types)
    mapped_input = station_path.exists()
    if mapped_input:
        print(f"Using saved charger locations: {station_path.name}", flush=True)
        stations = saved_station_table(station_path)
    else:
        stations = shared_data.load_chargers(states)
    records, details = charger_records(graph, stations, shared_data, network, mapped_input)
    print(f"Road input: {len(graph):,} intersections; {graph.number_of_edges():,} road segments")
    print(f"Charger input: {details['selected_station_records']:,} records; "
          f"{details['mapped_station_records']:,} mapped to {len(records):,} distinct intersections")
    start = endpoint_info(start_place, start_coordinates, graph, shared_data, max_endpoint_snap)
    goal = endpoint_info(goal_place, goal_coordinates, graph, shared_data, max_endpoint_snap)
    roads = RoadNetwork(graph)
    connections, reused = charger_connections(roads, records, full_range,
                                             Path(__file__).parent / "cache" / "full_map")
    trip_graph = assemble_trip(roads, records, connections, start, goal, starting_range, full_range)
    locations = dict(records, START=start, END=goal)
    coordinates = {key: (row["lat"], row["lon"]) for key, row in locations.items()}
    labels = {key: row["label"] for key, row in locations.items()}
    details.update(region=region, road_level=road_level, states=states,
                   street_source_file=street_path.name,
                   station_source_file=station_path.name if mapped_input else f"chargers_{'_'.join(states)}.csv",
                   used_saved_station_table=mapped_input, imported_precomputed_charger_edges=False,
                   road_vertices=len(graph), road_edges=graph.number_of_edges(),
                   cached_own_road_legs=reused, full_range=full_range, starting_range=starting_range,
                   start_snap_miles=start["snap_miles"], goal_snap_miles=goal["snap_miles"],
                   road_algorithm="own heap search", trip_algorithm="our A*", objective="total miles",
                   charging_rule="full recharge at every selected intermediate charger")
    return FullTrip(trip_graph, coordinates, labels, locations, graph, roads, details)


def road_route_shapes(trip, runs):
    """Reconstruct chosen road legs with our heap search, including access links."""
    shapes = {}
    for run in runs.values():
        if run["answer"] is None:
            continue
        path = run["answer"][0]
        for first, second in zip(path, path[1:]):
            if (first, second) in shapes:
                continue
            a, b = trip.locations[first], trip.locations[second]
            expected = trip.graph[first][second]
            if expected == 0 and (a["lat"], a["lon"]) == (b["lat"], b["lon"]):
                shapes[first, second] = [(a["lat"], a["lon"])] * 2
                continue
            road_limit = expected-a["snap_miles"]-b["snap_miles"]
            answer = trip.roads.path(trip.roads.index[a["road_node"]], trip.roads.index[b["road_node"]],
                                     cutoff=road_limit+1e-6)
            if answer is None or abs(answer[1]-road_limit) > 1e-5:
                raise ValueError("A selected leg could not be reconstructed with the same road mileage.")
            line = [(a["lat"], a["lon"])]
            road_nodes, _ = answer
            for u, v in zip(road_nodes, road_nodes[1:]):
                edge = trip.street_graph[u][v]
                if trip.street_graph.is_multigraph():
                    edge = min(edge.values(), key=lambda item: item["miles"])
                if "geometry" in edge:
                    points = [(float(y), float(x)) for x, y in edge["geometry"].coords]
                    origin = trip.street_graph.nodes[u]
                    if abs(points[-1][0]-origin["y"])+abs(points[-1][1]-origin["x"]) < abs(points[0][0]-origin["y"])+abs(points[0][1]-origin["x"]):
                        points.reverse()
                else:
                    points = [(trip.street_graph.nodes[n]["y"], trip.street_graph.nodes[n]["x"]) for n in (u,v)]
                line.extend(points)
            if len(road_nodes) == 1:
                node = trip.street_graph.nodes[road_nodes[0]]
                line.append((node["y"], node["x"]))
            line.append((b["lat"], b["lon"]))
            shapes[first, second] = line
    return shapes


def background_roads(graph, maximum=20000):
    """Thin background drawing only; all graph vertices/edges remain searchable."""
    candidates = []
    for u, v, edge in graph.edges(data=True):
        highway = edge.get("highway", "")
        kinds = highway if isinstance(highway, list) else [highway]
        if any(kind in ("motorway", "trunk") for kind in kinds):
            candidates.append((u, v, edge))
    stride = max(1, (len(candidates)+maximum-1)//maximum)
    lines = []
    for u, v, edge in candidates[::stride]:
        if "geometry" in edge:
            points = list(edge["geometry"].coords)
            step = max(1, (len(points)+59)//60)
            chosen = points[::step]
            if chosen[-1] != points[-1]:
                chosen.append(points[-1])
            lines.append([(float(y), float(x)) for x,y in chosen])
        else:
            lines.append([(graph.nodes[n]["y"], graph.nodes[n]["x"]) for n in (u,v)])
    return lines
