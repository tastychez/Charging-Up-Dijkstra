# Boston → Dallas in a Tesla: Dijkstra on a range-limited graph

**Question.** A Tesla drives from Boston to Dallas. Which Superchargers should it stop at
so that the total distance is as short as possible? The catch is the limited range: the car
cannot drive directly between every pair of stations.

![Dijkstra's search on the real map](figures/search_on_map.gif)

## Run it

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py               # analysis + all figures
.venv/bin/python main.py --show        # also play the search live in a window
.venv/bin/python main.py --range 300   # try another battery range (default 250)
```

`main.py` prints every Dijkstra step, the best route, and how the answer changes with range,
then writes the figures to `figures/`. The first run downloads the map and the road data
(1–2 minutes). After that, everything comes from `cache/`, so later runs take a few seconds
and work offline.

| File | What it does |
|---|---|
| `stations.py` | the 37 sites: Boston, Dallas, and 35 Supercharger sites in between |
| `realmap.py` | fetches the real map: OpenStreetMap tiles, plus driving distances and road shapes from OSRM |
| `dijkstra.py` | Dijkstra's algorithm, path traceback, and the range-limited charging graph |
| `visualize.py` | every figure, including the animation of the search on the map |
| `main.py` | runs the analysis and makes the figures |

To plan a different trip, edit `START`, `END` and `STATIONS` in `stations.py`, and the map
frame `BOUNDS` in `visualize.py`.

## Data

- **Stations.** Approximate locations of Supercharger sites along two corridors:
  - **Southern:** I-84 to Harrisburg, I-81 down the Shenandoah Valley, I-40 across Tennessee
    and Arkansas, then I-30 into Texas.
  - **Northern:** I-70 through Columbus, Indianapolis and St. Louis, then I-44 and US-69
    through Missouri and Oklahoma.
- **Road distances.** One request to the [OSRM](https://project-osrm.org) table service
  returns the real driving distance from every station to every other (37 × 37). OSRM
  measures each distance along the *fastest* route. A → B and B → A can differ slightly, so
  the graph is **directed**.
- **Map.** OpenStreetMap tiles, muted so the data stands out. The roads drawn on top are the
  real routes from the OSRM route service. Map data © OpenStreetMap contributors.
- Both services are free and public. The code identifies itself, waits a second between
  OSRM requests, and caches everything, as their usage policies ask.

## Model

**Nodes** are Boston, Dallas, and the 35 stations. There is an **edge A → B only if a
fully charged car can drive the road from A to B**: road distance ≤ range. Its **weight is
that road distance**. The battery limit lives in the structure of the graph, not in the
algorithm. An edge can pass other stations without stopping at them.

**Dijkstra.** Start at Boston with distance 0. At each step, *settle* the unsettled station
closest to Boston. Its distance is now final. Then *relax* its edges: if going through it
gives a neighbor a shorter distance, update that neighbor and remember where it came from
(`prev`). Stop when Dallas is settled, then follow `prev` back from Dallas to get the route.
When two routes are exactly the same length, the one with fewer stops wins.

## Result for a 250-mile range

The charging graph has 37 stations and 212 directed edges. The best route:

| Leg | Miles |
|---|---|
| Boston → Danbury, CT | 158 |
| Danbury → Harrisburg, PA | 236 |
| Harrisburg → Winchester, VA | 118 |
| Winchester → Wytheville, VA | 244 |
| Wytheville → Knoxville, TN | 182 |
| Knoxville → Nashville, TN | 179 |
| Nashville → Memphis, TN | 212 |
| Memphis → Little Rock, AR | 136 |
| Little Rock → Sulphur Springs, TX | 240 |
| Sulphur Springs → Dallas | 81 |
| **Total (9 charging stops)** | **1786** |

![Best route with a 250-mile range](figures/route.png)

The route takes the southern corridor the whole way. Driving non-stop would be 1762 miles,
so the nine charging stops add 24 miles of detours off the highway.

## The search, step by step

The animation at the top tells the story in four acts:

1. **The real map.** The 37 sites.
2. **Draw the graph.** Edges appear as the allowed distance grows to the full range.
3. **Dijkstra.** Each frame settles the closest station still in the queue (black ring) and
   relaxes its edges (orange). Blue dots are settled, and their distances are final. Orange
   circles are tentative. The strip at the bottom shows the priority queue.
4. **Trace back** from Dallas through `prev[]`, drawing each leg along the real roads.

The same steps as still images, for a printed report:

![Four moments of the search](figures/search_snapshots.png)

You can watch the two corridors race. Dijkstra settles stations in order of distance, so
it expands both corridors side by side. Breezewood, Columbus, Indianapolis, St. Louis,
Tulsa and the rest of the northern corridor are all settled before Dallas, at 480 to
1720 miles. Every one of them ends up off the final route. Dijkstra has no sense of
direction, so it has to settle all 37 stations before it reaches Dallas, the farthest one.
A heuristic search like A* aims toward Dallas and would explore far less of the northern
corridor.

## Varying the range

![Total miles and stops vs. range](figures/range_sweep.png)

| Range (mi) | Total miles | Stops | Stations settled | What changes |
|---|---|---|---|---|
| < 129 | — | — | — | no route |
| 129 | 1846 | 19 | 27 | Nashville → Jackson (129 mi) is the bottleneck |
| 176 | 1819 | 15 | 37 | Columbus → Indianapolis (176 mi) links up the northern corridor |
| 250 | 1786 | 9 | 37 | |
| 400 | 1767 | 5 | 37 | |
| 738 | 1762 | 2 | 37 | as short as driving non-stop |

![The charging graph at four ranges](figures/range_comparison.png)

What the sweep shows:

1. **Minimum range = the worst gap that cannot be avoided: 129 miles.** It is the stretch
   from Nashville to Jackson, TN. Below that, no path in the graph leads from Boston to
   Dallas. Finding the smallest range that still connects them is a
   *bottleneck* (minimax) path problem, a cousin of the shortest-path problem.
2. **The northern corridor never wins.** Below 176 miles it is not even connected, because
   Columbus → Indianapolis is 176 miles. Above that, Dijkstra explores it every time and
   rejects it every time. Even with unlimited range, going through St. Louis is 1808 miles,
   46 more than driving the southern corridor non-stop.
3. **Total distance never gets worse as range grows.** A larger range only *adds* edges, and
   adding edges can never make a shortest path longer.
4. **Range buys fewer detours.** Every stop means leaving the highway, so the total falls
   from 1846 miles at a 129-mile range to 1762 miles, the non-stop distance, at 738 miles.
5. **Stops do not always fall.** For example, a 235-mile range gives 10 stops and 1800 miles,
   while 213 miles gives 9 stops and 1802 miles. The objective is miles, so Dijkstra accepts
   an extra stop to save 2 miles.

## Limitations

- Station coordinates are approximate, at the town level, so the size of each stop's detour
  off the highway is approximate too. Exact Supercharger locations, for example from the
  AFDC station API that `data.py` at the repo root uses, would sharpen this.
- The model assumes a full charge at every stop and a fixed range. In reality range drops
  with speed, cold weather, and charging only to ~80%. A safety margin can be modeled by
  lowering the range.
- It minimizes distance, not travel time, and ignores charging time. The same algorithm
  works for time with a different edge weight (OSRM can also return durations).
- OSRM's distances follow the fastest route, which is not always the shortest, so they do
  not exactly satisfy the triangle inequality.
- The public OSRM server is fine for a class project but not for heavy use.
