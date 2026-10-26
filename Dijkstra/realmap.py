"""Fetch the real map: background tiles from OpenStreetMap, and road shapes for drawing
routes from the OSRM routing service. (The distances themselves come from data/, see network.py.)

Everything downloaded is cached in cache/, so only the first run needs the internet.
"""

import json
import time
import urllib.request
from functools import cache
from math import asinh, log, pi, radians, tan
from pathlib import Path

from PIL import Image

CACHE = Path(__file__).parent / "cache"
TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
ROUTE_URL = "https://router.project-osrm.org/route/v1/driving/{coords}?overview=full&geometries=geojson"
ATTRIBUTION = "Map © OpenStreetMap contributors · Roads: OSRM"
USER_AGENT = "Charging-Up-Dijkstra (discrete math class project)"

TILE_PIXELS = 256
EARTH_RADIUS_M = 6378137          # sphere used by Web Mercator


def mercator(lat, lon):
    """(lat, lon) in degrees -> Web Mercator (x, y) in meters, the projection map tiles use."""
    return EARTH_RADIUS_M * radians(lon), EARTH_RADIUS_M * log(tan(pi / 4 + radians(lat) / 2))


def _get(url):
    print(f"Downloading {url.split('?')[0][:90]}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def _osrm_coords(points):
    """(lat, lon) pairs -> "lon,lat;lon,lat", the order OSRM expects."""
    return ";".join(f"{lon},{lat}" for lat, lon in points)


def _tile(z, x, y):
    path = CACHE / "tiles" / f"{z}_{x}_{y}.png"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_get(TILE_URL.format(z=z, x=x, y=y)))
    tile = Image.open(path).convert("RGBA")
    return Image.alpha_composite(Image.new("RGBA", tile.size, "white"), tile).convert("RGB")


def basemap(south, west, north, east, zoom):
    """Stitch the map tiles covering a lat/lon box into one image.

    Returns (image, extent) ready for ax.imshow(image, extent=extent), in Web Mercator meters.
    Each zoom level doubles the detail; 6 or 7 suits a view of several states.
    """
    def tile_index(lat, lon):   # standard "slippy map" tile numbering
        n = 2 ** zoom
        return int((lon + 180) / 360 * n), int((1 - asinh(tan(radians(lat))) / pi) / 2 * n)

    (x0, y0), (x1, y1) = tile_index(north, west), tile_index(south, east)
    columns, rows = range(x0, x1 + 1), range(y0, y1 + 1)
    image = Image.new("RGB", (len(columns) * TILE_PIXELS, len(rows) * TILE_PIXELS))
    for i, x in enumerate(columns):
        for j, y in enumerate(rows):
            image.paste(_tile(zoom, x, y), (i * TILE_PIXELS, j * TILE_PIXELS))

    tile_m = 2 * pi * EARTH_RADIUS_M / 2 ** zoom
    left = -pi * EARTH_RADIUS_M + x0 * tile_m
    top = pi * EARTH_RADIUS_M - y0 * tile_m
    return image, (left, left + len(columns) * tile_m, top - len(rows) * tile_m, top)


@cache
def _routes():
    path = CACHE / "routes.json"
    return json.loads(path.read_text()) if path.exists() else {}


def road_shape(origin, destination):
    """The real road from one (lat, lon) point to another, as a list of (lat, lon) points.

    Fetched from OSRM the first time each leg is needed, then cached in cache/routes.json.
    """
    key = _osrm_coords([origin, destination])
    routes = _routes()
    if key not in routes:
        routes[key] = json.loads(_get(ROUTE_URL.format(coords=key)))["routes"][0]["geometry"]["coordinates"]
        CACHE.mkdir(exist_ok=True)
        (CACHE / "routes.json").write_text(json.dumps(routes))
        time.sleep(1)  # the public OSRM server asks for at most one request per second
    return [(lat, lon) for lon, lat in routes[key]]
