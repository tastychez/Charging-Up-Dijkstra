# Boston → Dallas in an EV: Dijkstra on a range-limited graph

**Question.** An electric car drives from Boston to Dallas. Which DC fast chargers should it
stop at so that the total distance is as short as possible? The catch is the limited range:
the car cannot drive directly between every pair of chargers.

![Dijkstra's search on the real map](figures/search_on_map.gif)

## Run it

This folder runs on the real charger network built at the repository root, so it uses the
root `.venv` and `data/` (see the root README: `charger_graph.py` builds `data/`).

```bash
../.venv/bin/python main.py               # analysis + all figures
../.venv/bin/python main.py --show        # also play the search live in a window
../.venv/bin/python main.py --range 240   # another range (default 200, up to 240)
../.venv/bin/python main.py --start "Buffalo, NY" --end "Springfield, MO"   # another trip
../.venv/bin/python trip_table.py         # slide table: search time and work per trip
```

Or run everything in one go: `./run_all.sh` (add `--quick` to skip `main.py`). It runs
`runtime.py`, `main.py` and `compare_library.py`, then opens the web demo and the figures.

**Web demo.** Open `dijkstra-demo.html` in any browser (no install, works offline). It replays
Dijkstra one line of code at a time, highlighting the line next to the map, the waitlist and
the distance table, and compares the real runtime with the slowed-down animation.
The source is in `web/` (TypeScript + React): `npm install`, then `npm run dev` to develop
or `npm run build:single` to rebuild `dijkstra-demo.html`.

**Runtime.** `../.venv/bin/python runtime.py` times a minimal Dijkstra on the real trip and on
random graphs from 1k to 64k nodes, and saves `figures/runtime.png`.

`main.py` prints Dijkstra's progress, the best route, and how the answer changes with range,
then writes the figures to `figures/`. The first run of a trip builds its network from `data/`
(about a minute) and caches it in `cache/` (`cache/network.pkl` for Boston → Dallas); it also
downloads the map tiles and the road shapes it draws. Later runs take about 15 seconds and
work offline. Figures for another trip get its name, e.g. `figures/route_buffalo_springfield.png`.

| File | What it does |
|---|---|
| `network.py` | loads the real network for a trip: every DC fast charger in the 17 states, and the road miles between them |
| `realmap.py` | fetches the map for the figures: OpenStreetMap tiles, and road shapes from OSRM |
| `dijkstra.py` | Dijkstra's algorithm, path traceback, and the range-limited charging graph |
| `hand.py` | our hand-written Dijkstra and A*, run on the same network |
| `visualize.py` | every figure, including the animation of the search on the map |
| `main.py` | runs the analysis and makes the figures |
| `runtime.py` | minimal Dijkstra plus a runtime function, timed on growing graphs |
| `compare_library.py` | our hand-written Dijkstra against NetworkX's and SciPy's at every range |
| `trip_table.py` | time, nodes expanded and edges checked for Boston → Dallas and Buffalo → Springfield |
| `web/` | TypeScript + React step-by-step demo; built into `dijkstra-demo.html` |
| `run_all.sh` | runs everything above and opens the demo |

## Data

- **Chargers.** Every public DC fast charger in the 17 states between Dallas and Boston,
  from the Department of Energy's station list (6,162 stations). Each is matched to its
  nearest road intersection; stations at the same intersection are merged, which leaves
  **4,971 charger locations**.
- **Distances.** Road miles between every two chargers at most 240 miles apart, measured on
  OpenStreetMap roads (4,218,013 legs). Each leg includes the short detour from the road to
  the charger at both ends. Roads can be one-way, so A → B and B → A can differ and the
  graph is **directed**. The start and end of a trip are joined to every charger within 240
  road miles.
- **Map.** OpenStreetMap tiles, muted so the data stands out. The roads drawn on top are the
  real routes from the OSRM route service. Map data © OpenStreetMap contributors.

## Model

**Range.** The range is the longest leg the car may drive on one charge. We only use 80% of
a full battery as a safety margin, so a Model Y's 250 miles gives a **200-mile range**. The
car is assumed to start with, and recharge to, those 200 miles at every stop.

**Nodes** are the start, the end, and the 4,971 chargers. There is an **edge A → B only if the
leg from A to B is at most the range**. Its **weight is the leg's miles**. The battery limit
lives in the structure of the graph, not in the algorithm. A leg can pass other chargers
without stopping. The data has legs up to 240 miles, so ranges up to 240 can be tested.

**Dijkstra.** Start at Boston with distance 0. At each step, *settle* the unsettled charger
closest to Boston. Its distance is now final. Then *relax* its edges: if going through it
gives a neighbor a shorter distance, update that neighbor and remember where it came from
(`prev`). Stop when Dallas is settled, then follow `prev` back from Dallas to get the route.

**Nodes expanded** is how many nodes Dijkstra settles before it reaches the end; **edges
checked** is how many edges it looks at while relaxing them. Both measure the search's work.

## Result for a 200-mile range

The charging graph has 4,973 nodes and 3,260,802 directed edges.
Dijkstra settles 4,268 of them before Dallas. The best route:

| Leg | Miles |
|---|---|
| Boston → Bronx, NY | 194.0 |
| Bronx → Avenel, NJ | 35.5 |
| Avenel → Bethesda, MD | 200.0 |
| Bethesda → Madison, VA | 86.9 |
| Madison → Fort Chiswell, VA | 194.5 |
| Fort Chiswell → Bristol, VA | 73.8 |
| Bristol → Knoxville, TN | 133.4 |
| Knoxville → Nashville, TN | 171.1 |
| Nashville → Brownsville, TN | 140.1 |
| Brownsville → West Memphis, AR | 61.2 |
| West Memphis → Little Rock, AR | 139.3 |
| Little Rock → Hope, AR | 100.2 |
| Hope → Rockwall, TX | 184.3 |
| Rockwall → Dallas | 22.7 |
| **Total (13 charging stops)** | **1,737.1** |

![Best route with a 200-mile range](figures/route.png)

The route takes the southern corridor: I-95 to Washington, I-81 down the Shenandoah Valley,
I-40 across Tennessee and Arkansas, and I-30 into Texas.

## The search, step by step

The animation at the top tells the story in three acts:

1. **The real network.** All 4,971 chargers.
2. **Dijkstra.** Each frame jumps ahead about 70 steps. Blue dots are settled (their distance
   is final), orange dots are waiting in the queue, gray dots are not reached yet, and the
   thin blue lines are the shortest-path tree (`prev`).
3. **Trace back** from Dallas through `prev[]`, drawing each leg along the real roads.

The same steps as still images, for a printed report:

![Four moments of the search](figures/search_snapshots.png)

Dijkstra settles chargers in order of distance from Boston, so the search spreads out like a
ripple in every direction: Chicago, Michigan and the whole Midwest are settled before Dallas,
and they all end up off the final route. Dijkstra has no sense of direction, so it settles
86% of the network before it reaches Dallas. A* (`hand.py`) aims toward Dallas and settles
3,457 instead of 4,268. The saving is modest here because the dense Northeast around Boston
has to be searched either way.

## Varying the range

![Total miles and stops vs. range](figures/range_sweep.png)

| Range (mi) | Total miles | Stops |
|---|---|---|
| 40 | — | — (no route) |
| 44 | 1,997.3 | 62 |
| 80 | 1,748.7 | 28 |
| 120 | 1,740.6 | 17 |
| 160 | 1,737.5 | 13 |
| 200 | 1,737.1 | 13 |
| 240 | 1,736.6 | 8 |

![Routes at four ranges](figures/range_comparison.png)

What the sweep shows:

1. **With real chargers, even a tiny range works.** Chargers are so dense that a 43-mile
   range already connects Boston to Dallas; at 44 miles the route needs 62 stops. Below 43
   miles some gap cannot be crossed. Finding that smallest workable range is a *bottleneck*
   (minimax) path problem, a cousin of the shortest-path problem.
2. **Total distance never gets worse as range grows.** A larger range only *adds* edges, and
   adding edges can never make a shortest path longer.
3. **Range mostly buys fewer stops, not fewer miles.** From a 120-mile range to 240 miles
   the trip gets only 4 miles shorter, but needs 9 fewer stops.
4. **Stops do not always fall.** A 184-mile range gives 12 stops, while 188 miles gives 13
   stops and 0.07 miles less. The objective is miles, so Dijkstra accepts an extra stop to
   save 0.07 miles. `trip.py` at the root instead puts fewest stops first.

## Hand-written vs library Dijkstra

`../.venv/bin/python compare_library.py` runs three Dijkstras on the same charging graph at
every range from 40 to 240 miles: ours (`dijkstra.py`), NetworkX's `single_source_dijkstra`
(pure Python) and SciPy's `csgraph.dijkstra` (compiled C). Only the search is timed.

| Range | Edges | Miles | Stops | Hand-written | NetworkX | SciPy |
|---|---|---|---|---|---|---|
| 80 | 1,022,730 | 1,748.7 | 28 | 50 ms | 93 ms | 1.5 ms |
| 160 | 2,385,776 | 1,737.4 | 13 | 113 ms | 212 ms | 3.7 ms |
| 200 | 3,260,802 | 1,737.1 | 13 | 150 ms | 286 ms | 4.8 ms |
| 240 | 4,219,580 | 1,736.6 | 8 | 193 ms | 366 ms | 5.7 ms |

![Each method's route at 200 miles](figures/library_routes.png)

![Search time of each method](figures/library_runtime.png)

- **Same answer.** At every range all three find the same distance and the same stops.
- **Ours beats NetworkX by about 2x.** Both are pure Python and stop at Dallas, but NetworkX
  looks up each edge's weight in an attribute dictionary and handles general cases, while
  ours reads a plain number from `{node: {neighbor: miles}}`.
- **SciPy is about 30x faster than ours** even though it finds the distance to *every*
  charger, not just Dallas: its loop runs in compiled C over arrays instead of Python dicts.
  The algorithm is the same; the constant factor is what differs.
- All three grow roughly in line with the number of edges, as O((V + E) log V) predicts.
  Timings are the fastest of 3 runs on an Apple laptop.

## Second trip: Buffalo → Springfield, MO

The same network and the same 200-mile range, from Buffalo, NY to Springfield, MO:
**931.7 miles with 5 charging stops**, at Rocky River, OH (mile 195), Findlay, OH (299),
Plainfield, IN (491), Vandalia, IL (652) and Sullivan, MO (782).

![Buffalo to Springfield with a 200-mile range](figures/route_buffalo_springfield.png)

The trip is half as long as Boston → Dallas, but the search does almost as much work:
Dijkstra settles everything closer to Buffalo than Springfield is, so it covers New England
and Virginia, behind the start, before it reaches Missouri.

![Dijkstra's search from Buffalo](figures/search_snapshots_buffalo_springfield.png)

`trip_table.py` puts both trips side by side (200-mile range, median of 101 runs):

| Trip | Dijkstra | Median time (ms) | Nodes expanded | Edges checked |
|---|---|---|---|---|
| Boston → Dallas | Hand-written | 149.68 | 4,268 | 3,001,774 |
| Boston → Dallas | NetworkX | 290.14 | 4,268 | 3,001,774 |
| Boston → Dallas | SciPy | 4.18 | 4,973 | 3,260,802 |
| Buffalo → Springfield | Hand-written | 140.49 | 3,868 | 2,893,605 |

Ours and NetworkX do exactly the same work; ours is faster per edge. SciPy does not stop at
the end, so it settles every node and checks every edge, and is still the fastest.

## Limitations

- The model assumes a full charge at every stop and a fixed range. In reality range drops
  with speed and cold weather. Using 80% of the battery (200 of 250 miles) is a simple
  safety margin.
- It minimizes distance, not travel time, and ignores charging time. The same algorithm
  works for time with a different edge weight.
- Every DC fast charger counts, whatever its network or plug type; a real car can only use
  the ones with a compatible plug.
