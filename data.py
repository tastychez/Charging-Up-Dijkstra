"""Download, cache, and combine the road network and EV charger data."""

import os
from pathlib import Path

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
# Every road a car can drive on. Only practical for a city-sized area.
ALL_ROADS = MAJOR_ROADS + ["secondary", "secondary_link", "tertiary", "tertiary_link",
                           "unclassified", "residential", "living_street"]

# City-sized areas cut out of a state file, as (state, (west, south, east, north)).
CITIES = {
    "boston": ("massachusetts", (-71.191, 42.227, -70.986, 42.400)),
}

GEOFABRIK_URL = "https://download.geofabrik.de/north-america/us/{region}-latest.osm.pbf"
AFDC_URL = "https://developer.nlr.gov/api/alt-fuel-stations/v1.json"


def _download(url, path):
    print(f"Downloading {url}")
    with requests.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        with open(path, "wb") as f:
            for chunk in response.iter_content(chunk_size=1 << 20):
                f.write(chunk)


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


def load_street_graph(region, road_types=MAJOR_ROADS):
    """Return the road network for a US state or a city in CITIES as a directed graph.

    `region` is a Geofabrik state name such as "massachusetts" or "rhode-island",
    or a city name from CITIES such as "boston".
    Vertices are intersections (with x = longitude, y = latitude).
    Edges are road segments with a `miles` attribute.
    """
    state, bbox = CITIES.get(region, (region, None))

    DATA_DIR.mkdir(exist_ok=True)
    graph_path = DATA_DIR / f"streets_{region}_{len(road_types)}types.graphml"
    if graph_path.exists():
        return ox.load_graphml(graph_path, edge_dtypes={"miles": float})

    pbf_path = DATA_DIR / f"{state}-latest.osm.pbf"
    if not pbf_path.exists():
        _download(GEOFABRIK_URL.format(region=state), pbf_path)

    osm_path = DATA_DIR / f"roads_{region}_{len(road_types)}types.osm"
    if not osm_path.exists():
        print("Extracting roads")
        _extract_roads(pbf_path, osm_path, road_types, bbox)

    print("Building graph")
    G = ox.graph_from_xml(osm_path, simplify=True)
    if bbox:
        G = ox.truncate.truncate_graph_bbox(G, bbox)
    for _, _, data in G.edges(data=True):
        data["miles"] = data["length"] / METERS_PER_MILE
    ox.save_graphml(G, graph_path)
    return G


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
