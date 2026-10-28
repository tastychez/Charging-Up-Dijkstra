"""David's heap-based A*, with a selectable heuristic and optional search counts."""

from heapq import heappop, heappush, nsmallest
from itertools import count
from math import isfinite

from heuristics import estimate_remaining_miles


def astar(graph, start, goal, heuristic=None, stats=None, trace=None, trace_compact=False):
    """Return (route, total_miles), or None when the goal is unreachable.

    Accept either {node: {neighbor: miles}} or the original NetworkX graphs
    with edge attribute 'miles'. For dictionary graphs, supply heuristic(node).
    The original NetworkX demo still defaults to its Haversine helper.

    A consistent heuristic gives the usual finite-graph heap runtime bound.
    The corridor runner prepares and checks this condition before calling us.
    Among exactly equal-distance paths, fewer driving legs win.
    Pass an empty trace list to record search steps for animation. Trace
    collection is optional and is excluded from the runner's timed searches.
    Compact traces retain the top 12 queued candidates and final predecessor/
    distance dictionaries, avoiding a full copy at every large-graph step.
    """
    if start not in graph or goal not in graph:
        raise ValueError("Both start and goal must be nodes in the graph.")
    if heuristic is None:
        heuristic = lambda node: estimate_remaining_miles(graph, node, goal)

    networkx_style = hasattr(graph, "is_multigraph")
    multiple_roads = networkx_style and graph.is_multigraph()
    g_score = {start: 0.0}
    hops = {start: 0}
    previous = {}
    order = count()
    start_h = float(heuristic(start))
    if not isfinite(start_h) or start_h < 0:
        raise ValueError("Heuristic estimates must be finite and nonnegative.")
    # (f=g+h, number of legs, tie-break serial, node, g when queued)
    frontier = [(start_h, 0, next(order), start, 0.0)]
    expanded_nodes = [] if trace is not None else None
    if trace is not None:
        trace.clear()

    def record_step(current, priority, updates, is_goal=False):
        if trace is None:
            return
        valid = [entry for entry in frontier if (entry[4], entry[1]) == (g_score[entry[3]], hops[entry[3]])]
        pending = nsmallest(12, valid) if trace_compact else sorted(valid)
        queued = [dict(node=node,g=distance,h=f-distance,f=f,legs=legs)
                  for f,legs,serial,node,distance in pending]
        step = dict(current=current, g=g_score[current], h=float(heuristic(current)),
                    f=priority, updates=updates, frontier=queued, frontier_count=len(valid),
                    expanded_count=len(expanded_nodes), is_goal=is_goal)
        if not trace_compact or is_goal:
            step.update(previous=dict(previous),distances=dict(g_score))
        if not trace_compact:
            step["expanded"] = list(expanded_nodes)
        trace.append(step)
    if stats is not None:
        stats.clear()
        stats.update(expanded=0, edge_checks=0, heap_pushes=1, stale_pops=0,
                     peak_frontier=1, expanded_order=[])

    while frontier:
        priority, queued_hops, _, current, queued_distance = heappop(frontier)
        if (queued_distance, queued_hops) != (g_score[current], hops[current]):
            if stats is not None:
                stats["stale_pops"] += 1
            continue
        if stats is not None:
            stats["expanded"] += 1  # Valid pops, including the destination.
            stats["expanded_order"].append(current)
        if trace is not None:
            expanded_nodes.append(current)
        if current == goal:
            record_step(current, priority, [], is_goal=True)
            route = [goal]
            while route[-1] != start:
                route.append(previous[route[-1]])
            route.reverse()
            return route, g_score[goal]

        updates = [] if trace is not None else None
        for neighbor, edge_data in graph[current].items():
            if multiple_roads:
                edge_miles = min(float(road["miles"]) for road in edge_data.values())
            elif networkx_style:
                edge_miles = float(edge_data["miles"])
            else:
                edge_miles = float(edge_data)
            if not isfinite(edge_miles) or edge_miles < 0:
                raise ValueError("A* requires finite, nonnegative edge distances.")
            if stats is not None:
                stats["edge_checks"] += 1
            candidate = (g_score[current] + edge_miles, hops[current] + 1)
            old = (g_score.get(neighbor, float("inf")), hops.get(neighbor, float("inf")))
            if candidate < old:
                h = float(heuristic(neighbor))
                if not isfinite(h) or h < 0:
                    raise ValueError("Heuristic estimates must be finite and nonnegative.")
                g_score[neighbor], hops[neighbor] = candidate
                previous[neighbor] = current
                heappush(frontier, (candidate[0] + h, candidate[1], next(order), neighbor, candidate[0]))
                if trace is not None:
                    updates.append(dict(node=neighbor, g=candidate[0], h=h, f=candidate[0]+h,
                                        previous=current))
                if stats is not None:
                    stats["heap_pushes"] += 1
                    stats["peak_frontier"] = max(stats["peak_frontier"], len(frontier))
        record_step(current, priority, updates)
    if trace is not None and trace_compact and trace:
        trace[-1].update(previous=dict(previous), distances=dict(g_score))
    return None
