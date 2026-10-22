"""Run two small A* examples with Haversine estimates and one destination.

City coordinates are real examples. The connections and road distances are
illustrative, not measurements of actual driving routes. No downloads needed.
"""

import networkx as nx

from astar import astar
from heuristics import estimate_remaining_miles


def make_demo_graph():
    graph = nx.MultiDiGraph()

    # Same attributes as data.py: x = longitude, y = latitude.
    locations = {
        "Boston": (42.3601, -71.0589),
        "Cambridge": (42.3736, -71.1097),
        "Medford": (42.4184, -71.1062),
        "Lynn": (42.4668, -70.9495),
        "Salem": (42.5195, -70.8967),
    }
    for name, (latitude, longitude) in locations.items():
        graph.add_node(name, x=longitude, y=latitude)

    # Illustrative distances in miles; each connection is available both ways.
    roads = [
        ("Cambridge", "Boston", 4),
        ("Cambridge", "Medford", 5),
        ("Boston", "Lynn", 14),
        ("Medford", "Lynn", 12),
        ("Lynn", "Salem", 6),
        ("Boston", "Salem", 25),
        ("Medford", "Salem", 20),
    ]
    for first, second, miles in roads:
        graph.add_edge(first, second, miles=miles)
        graph.add_edge(second, first, miles=miles)

    return graph


def main():
    graph = make_demo_graph()
    destination = "Salem"
    print("Small A* demo: example city coordinates and illustrative road distances.")
    print(f"Destination: {destination}")

    for start in ("Boston", "Cambridge"):
        estimate = estimate_remaining_miles(graph, start, destination)
        print(f"\nStart: {start}")
        print(f"Haversine estimate to destination: {estimate:.2f} miles")

        result = astar(graph, start, destination)
        if result is None:
            print("No route found.")
            continue

        route, distance = result
        print("A* route: " + " -> ".join(route))
        print(f"Total distance along graph edges: {distance:.2f} miles")


if __name__ == "__main__":
    main()
