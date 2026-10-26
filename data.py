"""Download, cache, and combine the road network and EV charger data."""

import os
import pickle
import time
from pathlib import Path

import networkx as nx
import numpy as np
import osmium
import osmnx as ox
import pandas as pd
import requests

DATA_DIR = Path(__file__).parent / "data"
METERS_PER_MILE = 1609.344

# Read AFDC_API_KEY from a local .env file (gitignored) if it isn't already set.
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() and key.strip() not in os.environ:
            os.environ[key.strip()] = value.strip()

# Road types to keep. Highways only keeps long-trip graphs small.
HIGHWAYS = ["motorway", "motorway_link", "trunk", "trunk_link"]
MAJOR_ROADS = HIGHWAYS + ["primary", "primary_link"]
# Highway ramps end on main and secondary roads, so a route graph needs those too.
# With highways only, about half the intersections in Massachusetts are dead ends.
ROUTE_ROADS = MAJOR_ROADS + ["secondary", "secondary_link"]
# Every road a car can drive on. Only practical for a city-sized area.
ALL_ROADS = ROUTE_ROADS + ["tertiary", "tertiary_link",
                           "unclassified", "residential", "living_street"]

ROAD_LEVELS = {"highways": HIGHWAYS, "major": MAJOR_ROADS, "route": ROUTE_ROADS, "all": ALL_ROADS}

# City-sized areas cut out of a state file, as (state, (west, south, east, north)).
CITIES = {
    "boston": ("massachusetts", (-71.191, 42.227, -70.986, 42.400)),
}

# Multi-state areas built by joining several state files.
# Dallas to Boston covers the three main ways to drive it:
#   I-30/I-40 (AR, TN) then I-81 (VA, WV, MD, PA) then I-84 (NY, CT)
#   I-44 (OK, MO) then I-70 (IL, IN, OH) then I-90 (PA, NY)
#   I-40 to Nashville then north through KY to OH
ROUTES = {
    "dallas-boston": ["texas", "oklahoma", "arkansas", "missouri", "tennessee",
                      "kentucky", "illinois", "indiana", "ohio", "virginia",
                      "west-virginia", "maryland", "pennsylvania", "new-jersey",
                      "new-york", "connecticut", "massachusetts"],
    # Second example. Its shortest route only uses these six states.
    "buffalo-springfield": ["new-york", "pennsylvania", "ohio", "indiana", "illinois", "missouri"],
}

STATE_CODES = {
    "arkansas": "AR", "connecticut": "CT", "illinois": "IL", "indiana": "IN",
    "kentucky": "KY", "maryland": "MD", "massachusetts": "MA", "missouri": "MO",
    "new-jersey": "NJ", "new-york": "NY", "ohio": "OH", "oklahoma": "OK",
    "pennsylvania": "PA", "rhode-island": "RI", "tennessee": "TN", "texas": "TX",
    "virginia": "VA", "west-virginia": "WV",
}


def region_states(region):
    """Return the two-letter state codes a region covers, for loading its chargers."""
    if region in ROUTES:
        return [STATE_CODES[s] for s in ROUTES[region]]
    state = CITIES[region][0] if region in CITIES else region
    return [STATE_CODES[state]]


GEOFABRIK_URL ="https://download.geofabrik.de/north-america/us/{region}-latest.osm.pbf"
AFDC_URL = "https://developer.nlr.gov/api/alt-fuel-stations/v1.json"
# US Census Bureau state outlines, simplified for maps (about 1 MB).
STATE_BORDERS_URL = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_state_20m.zip"


def _download(url, path, attempts=5):
    """Download url to path, retrying on network errors.

    Writes to a .part file first so a cut-off download is never mistaken for a full one.
    """
    part = path.with_suffix(path.suffix + ".part")
    for attempt in range(1, attempts + 1):
        print(f"Downloading {url}" + (f" (try {attempt})" if attempt > 1 else ""))
        try:
            with requests.get(url, stream=True, timeout=120) as response:
                response.raise_for_status()
                with open(part, "wb") as f:
                    for chunk in response.iter_content(chunk_size=1 << 20):
                        f.write(chunk)
            part.rename(path)
            return
        except requests.RequestException as error:
            part.unlink(missing_ok=True)
            if attempt == attempts:
                raise
            wait = 15 * attempt
            print(f"Download failed ({error.__class__.__name__}), retrying in {wait}s")
            time.sleep(wait)


def _extract_roads(pbf_path, osm_path, road_types, bbox=None):
    """Copy only the chosen road types (and the nodes they use) into an .osm file.

    If `bbox` is given, only keep roads with at least one point inside it.
    """
    road_filter = osmium.filter.TagFilter(*[("highway", t) for t in road_types])
    processor = osmium.FileProcessor(str(pbf_path), osmium.osm.NODE | osmium.osm.WAY)
    if bbox:
        processor = processor.with_locations()
    with osmium.BackReferenceWriter(str(osm_path), ref_src=str(pbf_path), overwrite=True) as writer:
        for obj in processor.with_filter(osmium.filter.EntityFilter(osmium.osm.WAY)).with_filter(road_filter):
            if bbox and not _touches_bbox(obj, bbox):
                continue
            writer.add_way(obj)


def _touches_bbox(way, bbox):
    west, south, east, north = bbox
    for node in way.nodes:
        if node.location.valid() and west <= node.lon <= east and south <= node.lat <= north:
            return True
    return False


def _state_roads_file(state, road_types, bbox=None, name=None):
    """Return an .osm file with the chosen roads of one state, extracting it if needed.

    State files we download only for this step are deleted afterwards to save disk space.
    """
    osm_path = DATA_DIR / f"roads_{name or state}_{len(road_types)}types.osm"
    if osm_path.exists():
        return osm_path

    pbf_path = DATA_DIR / f"{state}-latest.osm.pbf"
    downloaded_now = not pbf_path.exists()
    if downloaded_now:
        _download(GEOFABRIK_URL.format(region=state), pbf_path)

    print(f"Extracting roads from {state}")
    _extract_roads(pbf_path, osm_path, road_types, bbox)
    if downloaded_now and not bbox:
        pbf_path.unlink()
    return osm_path


def load_street_graph(region, road_types=MAJOR_ROADS):
    """Return the road network for a region as a directed graph.

    `region` is a Geofabrik state name ("massachusetts", "rhode-island"),
    a city from CITIES ("boston"), or a multi-state route from ROUTES ("omaha-boston").
    Vertices are intersections (with x = longitude, y = latitude).
    Edges are road segments with a `miles` attribute.

    The graph is cleaned so routing can never get stuck: roads that loop back to
    the same intersection are removed, and only the largest strongly connected
    piece is kept, so every intersection can be reached from every other one.
    """
    DATA_DIR.mkdir(exist_ok=True)
    graph_path = DATA_DIR / f"streets_{region}_{len(road_types)}types.pkl"
    if graph_path.exists():
        with open(graph_path, "rb") as f:
            return pickle.load(f)

    if region in ROUTES:
        # OpenStreetMap ids are shared across state files, so roads that cross
        # a state line join up when the state graphs are combined. A road that
        # crosses a state line is in both files, and its points have to stay
        # vertices in both state graphs. Otherwise each state simplifies the road
        # differently, the two halves share no vertex, and the crossing is lost
        # (this broke eastbound I-40 over the Mississippi at Memphis).
        osm_paths = [_state_roads_file(state, road_types) for state in ROUTES[region]]
        shared = _shared_node_ids(osm_paths)
        graphs = []
        for osm_path in osm_paths:
            g = ox.graph_from_xml(osm_path, simplify=False, retain_all=True)
            nx.set_node_attributes(g, {n: True for n in g if n in shared}, "border")
            graphs.append(ox.simplify_graph(g, node_attrs_include=["border"]))
        print("Joining states")
        G = nx.compose_all(graphs)
    else:
        state, bbox = CITIES.get(region, (region, None))
        osm_path = _state_roads_file(state, road_types, bbox, name=region)
        print("Building graph")
        G = ox.graph_from_xml(osm_path, simplify=True)
        if bbox:
            G = ox.truncate.truncate_graph_bbox(G, bbox)

    G = clean_graph(G)
    with open(graph_path, "wb") as f:
        pickle.dump(G, f, protocol=pickle.HIGHEST_PROTOCOL)
    return G


def _shared_node_ids(osm_paths):
    """Ids of the points that appear in more than one state file (roads crossing a state line)."""
    ids = []
    for path in osm_paths:
        ids.append(np.fromiter((n.id for n in osmium.FileProcessor(str(path), osmium.osm.NODE)), dtype=np.int64))
    values, counts = np.unique(np.concatenate(ids), return_counts=True)
    return set(values[counts > 1].tolist())


def clean_graph(G):
    """Make the street graph safe for routing.

    - OpenStreetMap occasionally stores one intersection as two points at the exact
      same spot joined by a road of length 0. Those pairs are merged into one intersection.
    - Roads that loop back to the same intersection are removed.
    - Only the largest strongly connected piece is kept, so every intersection can
      be reached from every other one.
    """
    for u, v in [(u, v) for u, v, d in G.edges(data=True) if d["length"] <= 0]:
        if u != v and u in G and v in G:
            nx.contracted_nodes(G, u, v, self_loops=False, copy=False)
    G.remove_edges_from(list(nx.selfloop_edges(G)))
    G = ox.truncate.largest_component(G, strongly=True)
    for _, _, data in G.edges(data=True):
        data["miles"] = data["length"] / METERS_PER_MILE
    return G


def routing_graph(G):
    """Return a simple directed graph for shortest-path algorithms.

    OpenStreetMap sometimes has two road segments between the same pair of
    intersections. This keeps only the shorter one, so G[u][v]["miles"] is
    always the length of the best road from u to v.
    """
    return ox.convert.to_digraph(G, weight="miles")


def load_chargers(states):
    """Return public DC fast charging stations in the given states as a DataFrame."""
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / f"chargers_{'_'.join(states)}.csv"
    if path.exists():
        return pd.read_csv(path)

    params = {
        "api_key": os.environ.get("AFDC_API_KEY", "DEMO_KEY"),
        "fuel_type": "ELEC",
        "ev_charging_level": "dc_fast",
        "status": "E",
        "access": "public",
        "state": ",".join(states),
        "limit": "all",
    }
    response = requests.get(AFDC_URL, params=params, timeout=60)
    response.raise_for_status()
    stations = response.json()["fuel_stations"]

    columns = ["id", "station_name", "latitude", "longitude", "city", "state",
               "ev_network", "ev_dc_fast_num"]
    df = pd.DataFrame(stations)[columns]
    df.to_csv(path, index=False)
    return df


def load_state_borders(states):
    """Return the outlines of the given states (two-letter codes) as a GeoDataFrame, for maps only."""
    import geopandas as gpd

    path = DATA_DIR / "us_states_20m.zip"
    if not path.exists():
        DATA_DIR.mkdir(exist_ok=True)
        _download(STATE_BORDERS_URL, path)
    borders = gpd.read_file(path)
    return borders[borders["STUSPS"].isin(states)].to_crs("EPSG:4326")


def snap_chargers(G, chargers, max_snap_miles=2.0):
    """Match each charger to its nearest intersection in G.

    Adds `node` and `snap_miles` columns, and drops chargers farther than
    `max_snap_miles` from the road network (they are off our map).
    """
    nodes, dists = ox.distance.nearest_nodes(
        G, X=chargers["longitude"], Y=chargers["latitude"], return_dist=True
    )
    chargers = chargers.copy()
    chargers["node"] = nodes
    chargers["snap_miles"] = [d / METERS_PER_MILE for d in dists]
    return chargers[chargers["snap_miles"] <= max_snap_miles].reset_index(drop=True)
