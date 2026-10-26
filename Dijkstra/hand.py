from heapq import heappop, heappush   # heappop, heappush
from itertools import count           # used to create order
from math import asin, cos, inf, radians, sin, sqrt   # inf = infinity


def rebuild(previous, start, goal):
    route = [goal]
    while route[-1] != start:
        route.append(previous[route[-1]])
    return route[::-1]


def dijkstra(graph, source, target):
    best = {source: (0, 0)}            # node -> (miles, legs)
    prev, settled = {}, set()
    heap = [(0, 0, source)]            # waitlist, closest first

    while heap:
        miles, legs, u = heappop(heap) # closest unsettled node
        if u in settled:
            continue                   # outdated entry
        settled.add(u)                 # its distance is now final
        if u == target:
            break
        for v, w in graph[u].items():  # relax every road out of u
            cand = (miles + w, legs + 1)
            if v not in settled and (v not in best or cand < best[v]):
                best[v] = cand
                prev[v] = u
                heappush(heap, (*cand, v))
    return best, prev


def astar(graph, start, goal, h):
    order = count()                               # tie-break, fresh for every search
    g = {start: 0.0}; hops = {start: 0}; previous = {}
    # (f = g + h, legs, tie-break, node, g when queued)
    frontier = [(h(start), 0, next(order), start, 0.0)]

    while frontier:
        f, legs, _, cur, g_q = heappop(frontier)
        if (g_q, legs) != (g[cur], hops[cur]):
            continue                              # outdated entry
        if cur == goal:
            return rebuild(previous, start, goal), g[goal]
        for nb, miles in graph[cur].items():
            cand = (g[cur] + miles, hops[cur] + 1)
            if cand < (g.get(nb, inf), hops.get(nb, inf)):
                g[nb], hops[nb] = cand
                previous[nb] = cur
                heappush(frontier,
                         (cand[0] + h(nb), cand[1], next(order), nb, cand[0]))
    return None                                   # goal unreachable


def straight_line_miles(a, b):
    """Great-circle miles between two (lat, lon) points: A*'s guess, never too long."""
    lat1, lon1, lat2, lon2 = map(radians, (*a, *b))
    x = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * 3958.7 * asin(sqrt(x))     # Earth radius in miles, rounded down so h never overestimates


if __name__ == "__main__":
    # Boston → Dallas on the real network (about 5,000 chargers), 200-mile range.
    from dijkstra import charging_graph
    from network import END, START, load_network

    coords, cities, _, legs = load_network()
    graph = charging_graph(legs, 200)

    best, prev = dijkstra(graph, START, END)
    print(f"Dijkstra: {best[END][0]:,.1f} miles,", " → ".join(cities[v] for v in rebuild(prev, START, END)))

    h = lambda node: straight_line_miles(coords[node], coords[END])
    route, miles = astar(graph, START, END, h)
    print(f"A*:       {miles:,.1f} miles,", " → ".join(cities[v] for v in route))
