"""The real charging network: every public DC fast charger between Boston and Dallas.

The data comes from the repository root (data/, built by charger_graph.py):
about 5,000 charger locations in 17 states from the Department of Energy's station
list, and the road miles between every two of them that are at most 240 miles apart,
measured on OpenStreetMap roads. Each leg includes
the short detour from the road to the charger at both ends. The start and end of a
trip are joined to every charger within 240 road miles.

The first call for a trip takes about a minute; the result is cached in cache/
(cache/network.pkl for Boston to Dallas).
"""

import pickle
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(__file__).parent / "cache" / "network.pkl"

START = "Boston, MA"
END = "Dallas, TX"
# A range here is the longest leg the car may drive: 80 percent of a full charge, so a
# Model Y's 250 miles gives 200. data/ has legs up to 240 miles.
MAX_RANGE = 240


def cache_path(start, end):
    if (start, end) == (START, END):
        return CACHE
    slug = lambda place: re.sub(r"[^a-z]+", "_", place.lower()).strip("_")
    return CACHE.with_name(f"network_{slug(start)}_to_{slug(end)}.pkl")


def load_network(start=START, end=END):
    """Return (coords, cities, names, legs) for the whole network, from start to end.

    coords[v] = (lat, lon) and cities[v] = "City, ST" for every vertex v; names[v] is
    the charger's name. legs[u] = (miles, neighbors): the legs out of u, shortest first.
    Chargers are named by their street-graph id as a string; the ends by their place names.
    """
    cache = cache_path(start, end)
    if cache.exists():
        with open(cache, "rb") as f:
            return pickle.load(f)

    sys.path.insert(0, str(ROOT))
    import trip  # root module: needs the root .venv and data/

    # trip.py takes the full range and keeps legs up to 80 percent of it.
    T = trip.plan_trip(start, end, MAX_RANGE / trip.BUFFER)["trip_graph"]
    vid = {"START": start, "END": end}
    vid.update({n: str(n) for n in T if n not in vid})

    coords, cities, names, legs = {}, {}, {}, {}
    for n, d in T.nodes(data=True):
        v = vid[n]
        coords[v] = (d["lat"], d["lon"])
        cities[v] = d["name"] if n in ("START", "END") else f"{d['city']}, {d['state']}"
        names[v] = d["name"]
        row = sorted((m["miles"], vid[b]) for b, m in T[n].items())
        legs[v] = ([m for m, _ in row], [b for _, b in row])

    network = coords, cities, names, legs
    cache.parent.mkdir(exist_ok=True)
    with open(cache, "wb") as f:
        pickle.dump(network, f, protocol=pickle.HIGHEST_PROTOCOL)
    return network
