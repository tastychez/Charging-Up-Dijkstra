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


def astar(graph, start, goal, h):
    g = {start: 0.0}; hops = {start: 0}; previous = {}
    # (f = g + h, legs, tie-break, node, g when queued)
    frontier = [(h(start), 0, next(order), start, 0.0)]

    while frontier:
        f, legs, _, cur, g_q = heappop(frontier)
        if (g_q, legs) != (g[cur], hops[cur]):
            continue                              # outdated entry
        if cur == goal:
            return rebuild(previous), g[goal]
        for nb, miles in graph[cur].items():
            cand = (g[cur] + miles, hops[cur] + 1)
            if cand < (g.get(nb, inf), hops.get(nb, inf)):
                g[nb], hops[nb] = cand
                previous[nb] = cur
                heappush(frontier,
                         (cand[0] + h(nb), cand[1], next(order), nb, cand[0]))
    return None                                   # goal unreachable
