"""Build the charger graph on top of a street graph.

Vertices are charging stations. An edge u -> v means a car can drive from
charger u to charger v on one charge. Its weight is the miles of that leg:

    miles = snap(u) + road miles from u's intersection to v's intersection + snap(v)

snap(c) is the straight-line distance from a charger to the intersection it was
matched to. Counting it on the way in and on the way out means every charging
stop costs 2 x snap(c) extra miles, so chargers that are out of the way cost more.

The road miles between chargers are computed once with SciPy's published
Dijkstra (scipy.sparse.csgraph) and saved. Our own Dijkstra and A* then run on
the finished street graph and charger graph.

Usage:
    python charger_graph.py                       # builds dallas-boston
    python charger_graph.py --region massachusetts --roads major
"""

import argparse
import pickle
import time

import networkx as nx
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

import data

# The longest leg any car in our experiments can drive: 300 mile range x 80 percent.
MAX_LEG_MILES = 300 * 0.8
# Tiny weight for the few road segments OpenStreetMap gives a length of 0,
# so SciPy still treats them as roads.
MIN_EDGE_MILES = 1e-6


def street_matrix(G):
    """Turn a street graph into a SciPy sparse matrix for fast shortest paths.

    Returns (matrix, nodes, index) where matrix[i, j] is the miles of the
    shortest road from nodes[i] to nodes[j], and index maps a node id to its row.
    """
    D = data.routing_graph(G)
    nodes = np.array(list(D.nodes))
    index = {n: i for i, n in enumerate(nodes)}
    rows, cols, miles = [], [], []
    for u, v, d in D.edges(data=True):
        rows.append(index[u])
        cols.append(index[v])
        miles.append(max(d["miles"], MIN_EDGE_MILES))
    matrix = csr_matrix((miles, (rows, cols)), shape=(len(nodes), len(nodes)))
    return matrix, nodes, index


def charger_stations(G, region):
    """Return one row per intersection that has a charger matched to it.

    If several chargers match the same intersection, the closest one is kept
    (it has the smallest detour) and `stations` counts how many share it.
    """
    chargers = data.snap_chargers(G, data.load_chargers(data.region_states(region)))
    chargers = chargers.sort_values("snap_miles")
    counts = chargers.groupby("node").size().rename("stations")
    best = chargers.drop_duplicates("node").set_index("node").join(counts)
    return best.reset_index()


def build_charger_graph(region="dallas-boston", road_types=data.ROUTE_ROADS, batch=50):
    """Compute every charger-to-charger leg up to MAX_LEG_MILES and save it."""
    t0 = time.time()
    G = data.load_street_graph(region, road_types)
    matrix, nodes, index = street_matrix(G)
    stations = charger_stations(G, region)
    rows = np.array([index[n] for n in stations["node"]])
    snap = stations["snap_miles"].to_numpy()
    print(f"Street graph: {len(nodes):,} intersections. Charger intersections: {len(rows):,}")

    sources, targets, road = [], [], []
    for start in range(0, len(rows), batch):
        chunk = rows[start:start + batch]
        dist = dijkstra(matrix, directed=True, indices=chunk, limit=MAX_LEG_MILES)[:, rows]
        for i in range(len(chunk)):
            leg = snap[start + i] + dist[i] + snap
            ok = np.isfinite(dist[i]) & (leg <= MAX_LEG_MILES)
            ok[start + i] = False
            js = np.nonzero(ok)[0]
            sources.append(np.full(len(js), start + i, dtype=np.int32))
            targets.append(js.astype(np.int32))
            road.append(dist[i][js].astype(np.float32))
        done = min(start + batch, len(rows))
        print(f"  {done:,}/{len(rows):,} chargers ({time.time() - t0:.0f}s)", end="\r")
    print()

    edges = pd.DataFrame({
        "source": np.concatenate(sources),
        "target": np.concatenate(targets),
        "road_miles": np.concatenate(road),
    })
    edges["miles"] = snap[edges["source"]] + edges["road_miles"] + snap[edges["target"]]

    path = data.DATA_DIR / f"chargers_{region}_{len(road_types)}types.pkl"
    with open(path, "wb") as f:
        pickle.dump({"stations": stations, "edges": edges, "max_leg_miles": MAX_LEG_MILES}, f)
    print(f"Saved {len(edges):,} charger-to-charger legs to {path.name} in {time.time() - t0:.0f}s")
    return stations, edges


def load_charger_graph(region="dallas-boston", usable_miles=250 * 0.8, road_types=data.ROUTE_ROADS):
    """Return the charger graph for a car that can drive `usable_miles` per leg.

    Vertices are the street-graph intersection ids of the chargers, with
    attributes name, city, state, lat, lon, snap_miles and stations.
    Edges have `miles` (the full leg, including both detours) and `road_miles`.
    """
    path = data.DATA_DIR / f"chargers_{region}_{len(road_types)}types.pkl"
    if not path.exists():
        build_charger_graph(region, road_types)
    with open(path, "rb") as f:
        saved = pickle.load(f)
    if usable_miles > saved["max_leg_miles"]:
        raise ValueError(f"Legs were only computed up to {saved['max_leg_miles']} miles")

    stations, edges = saved["stations"], saved["edges"]
    C = nx.DiGraph()
    for row in stations.itertuples():
        C.add_node(row.node, name=row.station_name, city=row.city, state=row.state,
                   lat=row.latitude, lon=row.longitude, snap_miles=row.snap_miles,
                   stations=row.stations)
    ids = stations["node"].to_numpy()
    keep = edges[edges["miles"] <= usable_miles]
    C.add_edges_from(
        (ids[s], ids[t], {"miles": float(m), "road_miles": float(r)})
        for s, t, m, r in zip(keep["source"], keep["target"], keep["miles"], keep["road_miles"])
    )
    return C


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="dallas-boston")
    parser.add_argument("--roads", choices=list(data.ROAD_LEVELS), default="route")
    args = parser.parse_args()
    build_charger_graph(args.region, data.ROAD_LEVELS[args.roads])


if __name__ == "__main__":
    main()
