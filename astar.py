"""Initial A* implementation for the project's NetworkX road graphs."""

from heapq import heappop, heappush
from itertools import count

from heuristics import estimate_remaining_miles


def astar(graph, start, goal):
    """Return (route, total_miles), or None when the goal is unreachable.

    Nodes need x=longitude and y=latitude in degrees. Edges need nonnegative
    miles weights. The Haversine estimate must not exceed the true remaining
    route cost for A* to guarantee a shortest route.

    Works with Graph, DiGraph, MultiGraph, and MultiDiGraph. Battery limits
    are a later addition; this first version searches the supplied edges.
    """
    if start not in graph or goal not in graph:
        raise ValueError("Both start and goal must be nodes in the graph.")

    # g_score records the shortest distance found so far from the start.
    g_score = {start: 0.0}
    previous = {}
    order = count()  # Break ties without comparing node IDs.

    # Heap entries: (f = g + h, tie-break number, node, g when queued).
    frontier = [
        (estimate_remaining_miles(graph, start, goal), next(order), start, 0.0)
    ]

    while frontier:
        _, _, current, queued_distance = heappop(frontier)

        # A better route may have been queued after this entry was created.
        if queued_distance > g_score[current]:
            continue

        if current == goal:
            route = [goal]
            while route[-1] != start:
                route.append(previous[route[-1]])
            route.reverse()
            return route, g_score[goal]

        for neighbor, edge_data in graph[current].items():
            # A road graph can have several roads between the same two nodes.
            roads = edge_data.values() if graph.is_multigraph() else (edge_data,)
            lengths = [float(road["miles"]) for road in roads]
            if any(length < 0 for length in lengths):
                raise ValueError("A* requires nonnegative road distances.")
            edge_miles = min(lengths)
            new_distance = g_score[current] + edge_miles

            if new_distance < g_score.get(neighbor, float("inf")):
                g_score[neighbor] = new_distance
                previous[neighbor] = current
                heuristic = estimate_remaining_miles(graph, neighbor, goal)
                priority = new_distance + heuristic
                heappush(
                    frontier,
                    (priority, next(order), neighbor, new_distance),
                )

    return None
