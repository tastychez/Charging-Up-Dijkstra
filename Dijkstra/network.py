"""The real charging network: every public DC fast charger between Boston and Dallas.

The data comes from the repository root (data/, built by charger_graph.py):
about 5,000 charger locations in 17 states from the Department of Energy's station
list, and the road miles between every two of them that are at most 240 miles apart,
measured on OpenStreetMap roads. Each leg includes
the short detour from the road to the charger at both ends. Boston and Dallas are
joined to every charger within 240 road miles.

The first call takes about 15 seconds; the result is cached in cache/network.pkl.
"""

import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(__file__).parent / "cache" / "network.pkl"

START = "Boston, MA"
END = "Dallas, TX"
# A range here is the longest leg the car may drive: 80 percent of a full charge, so a
# Model Y's 250 miles gives 200. data/ has legs up to 240 miles.
MAX_RANGE = 240


def load_network():
    """Return (coords, cities, names, legs) for the whole network.

    coords[v] = (lat, lon) and cities[v] = "City, ST" for every vertex v; names[v] is
    the charger's name. legs[u] = (miles, neighbors): the legs out of u, shortest first.
    Chargers are named by their street-graph id as a string; the ends by START and END.
    """
    if CACHE.exists():
        with open(CACHE, "rb") as f:
            return pickle.load(f)

    sys.path.insert(0, str(ROOT))
    import trip  # root module: needs the root .venv and data/

    T = trip.plan_trip(START, END, MAX_RANGE)["trip_graph"]
    vid = {"START": START, "END": END}
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
    CACHE.parent.mkdir(exist_ok=True)
    with open(CACHE, "wb") as f:
        pickle.dump(network, f, protocol=pickle.HIGHEST_PROTOCOL)
    return network
